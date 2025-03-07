from functools import partial
import numpy as np
import tensorflow as tf

from cmorl.utils.loss_composition import clip_to, curriculum, importance, inv_mean, offset, p_mean, then, weaken
from cmorl.utils.reward_utils import  CMORL, Transition
from gymnasium.envs.box2d.lunar_lander import LunarLander
from gymnasium.envs.mujoco.reacher import ReacherEnv
from gymnasium.envs.mujoco.mujoco_env import MujocoEnv

from envs.Bittle.opencat_gym_env import OpenCatGymEnv

def mujoco_multi_dim_reward_joints_x_velocity(transition: Transition, env: MujocoEnv, speed_multiplier=1.0, action_multiplier=1.0):
    action = np.clip((1.0 - tf.abs(transition.action*action_multiplier)**2.0), 0.0, 1.0)
    if not hasattr(env, "prev_xpos"):
        env.prev_xpos = np.copy(env.data.xpos) # type: ignore
    x_velocities = (env.data.xpos - env.prev_xpos) / env.dt # type: ignore
    env.prev_xpos = np.copy(env.data.xpos) # type: ignore
    # slow_speed = np.clip(x_velocities[1:, 0]*speed_multiplier*3, 0.0, 1.0)
    speed = np.clip(x_velocities[1:, 0]*speed_multiplier, 0.0, 1.0)
    return np.hstack([speed, action])


def mujoco_CMORL(num_actions, speed_multiplier=1.0, action_multiplier=1.0):
    @tf.function
    def mujoco_composer(q_values, p_batch=0.0, p_objectives=-4.0):
        q_x_batch = tf.transpose(q_values)
        speed_batch =p_mean(q_x_batch[0:-num_actions], p=-1.0, axis=0)
        action_batch = tf.clip_by_value(p_mean(q_x_batch[-num_actions:], p=0.0, axis=0), 0.0, 1.0)
        combined_batch = p_mean([speed_batch, action_batch], p=p_objectives, axis=0)
        combined = p_mean(combined_batch, p=p_batch, axis=0)
        # qs_c = p_mean(q_values, p=p_batch, axis=0)
        # speed = p_mean(qs_c[0:-num_actions], p=-2.0)
        # action = tf.clip_by_value(p_mean(qs_c[-num_actions:], p=0.0)/0.7, 0.0, 1.0)
        # q_c = then(forward, action, slack=0.5) 
        # q_c = forward
        # q_c = p_mean([speed, action], p=p_objectives)
        return p_mean([speed_batch, action_batch], p=1.0, axis=-1), combined
    return CMORL(partial(mujoco_multi_dim_reward_joints_x_velocity, speed_multiplier=speed_multiplier, action_multiplier=action_multiplier), mujoco_composer)

def halfcheetah_CMORL():
    num_actions = 6
    def reward(transition: Transition, env: MujocoEnv):
        action = (1.0 - transition.action**2.0)
        if not hasattr(env, "prev_xpos"):
            env.prev_xpos = np.copy(env.data.xpos) # type: ignore
        x_velocities = (env.data.xpos - env.prev_xpos) / env.dt # type: ignore
        env.prev_xpos = np.copy(env.data.xpos) # type: ignore
        speed = x_velocities[1:, 0]
        slow = p_mean(np.clip(speed, 0.0, 1.0),0.0)**0.5
        fast = p_mean(np.clip(speed*0.2, 0.0, 1.0), 0.0)
        return np.hstack([slow, fast, action])

    @tf.function
    def composer(q_values, p_batch=0, p_objectives=-4.0):
        qs_c = p_mean(q_values, p=p_batch, axis=0)
        slow = qs_c[0]
        fast = qs_c[1]
        action = p_mean(qs_c[-num_actions:], p=-1.0)
        # q_c = then(forward, action, slack=0.5) 
        # q_c = forward
        # q_c = curriculum([action, slow, fast], slack=0.3, p=p_objectives)
        q_c = then(slow, p_mean([action**0.5, fast], p=p_objectives))
        return tf.stack([action, slow, fast]), q_c
    return CMORL(reward, composer)

def walker_CMORL(speed_multiplier=0.5):
    @tf.function
    def walker_composer(q_values, p_batch=0, p_objectives=-4.0):
        qs_c = p_mean(q_values, p=p_batch, axis=0)
        speed = p_mean(qs_c[0:-6], p=0.0)
        action = p_mean(qs_c[-6:], p=0.0)
        # q_c = then(forward, action, slack=0.5) 
        # q_c = forward
        q_c = p_mean([speed, action], p=p_objectives)
        return tf.stack([speed, action]), q_c
    return CMORL(partial(mujoco_multi_dim_reward_joints_x_velocity, speed_multiplier=speed_multiplier), walker_composer)


def bittle_rw(transition: Transition, env: OpenCatGymEnv):
    action_rw = (1.0 - np.abs(transition.action))
    forward = transition.info.get("forward", 0.0)
    change_direction = transition.info.get("change_direction", env.action_space.low*0.0)
    body_stability = transition.info.get("body_stability", np.zeros(3))
    # return np.hstack([[forward], change_direction, action_rw])
    return np.hstack([[forward], change_direction])
    # return np.array([forward])

def composed_reward_fn(transition, env):
    rew_vec = mujoco_multi_dim_reward_joints_x_velocity(transition, env)
    reward = p_mean(rew_vec, p=-4.0)
    return reward

def multi_dim_reacher(transition: Transition, env: ReacherEnv) -> np.ndarray:
    reward_performance = 1.0 - np.clip(np.linalg.norm(transition.next_state[-3:-1])/0.4, 0.0, 1.0)
    reward_actuation = np.clip((1 - (transition.action/0.4)**2.0), 0.0, 1.0)
    # print(transition.next_state[-3:-1])
    # print("rw:", reward_performance)
    rw_vec = np.concatenate([[reward_performance], reward_actuation], dtype=np.float32)
    return rw_vec

@tf.function
def reacher_composer(q_values, p_batch=0, p_objectives=-1.0):
    qs_batch = tf.transpose(q_values)
    reach = qs_batch[0]**2.0
    smoothness = p_mean(qs_batch[1:], p=0.0, axis=0)
    combined = p_mean([reach, smoothness], p=p_objectives, axis=0)
    q_c = p_mean(combined, p=p_batch, axis=0)
    return p_mean([smoothness, reach], p=p_batch, axis=-1), q_c

reacher_cmorl = CMORL(
    multi_dim_reacher, reacher_composer 
)

def normed_angular_distance(a, b):
    diff = (b - a + np.pi) % (2 * np.pi) - np.pi
    return np.abs(diff + 2 * np.pi if diff < -np.pi else diff) / np.pi

def multi_dim_pendulum(transition: Transition, env, setpoint) -> np.ndarray:
    # check if action is an array or a scalar
    u = np.squeeze(transition.action)
    th, thdot = env.state  # th := theta
    angle_rw = 1.0 - tf.clip_by_value(normed_angular_distance(th, setpoint)*2.0, 0.0, 1.0)

    # Normalizing the torque to be in the range [0, 1]
    normalized_u = abs(u / env.max_torque)
    actuation_rw = 1.0 - normalized_u**2.0
    
    # Merge the angle reward and the normalized torque into a single reward vector
    thdot_rw = 1.0 - np.abs(thdot) / env.max_speed
    rw_vec = np.array([angle_rw, actuation_rw], dtype=np.float32)
    return rw_vec

# APS Specification for Pendulum:
# 
# \begin{align}
# \phi_{\text{pendulum}} = \text{angle} \land_{p=-1.0} \text{actuation}
# \end{align}
#
# This specification represents a conjunction between the angle alignment and 
# minimal actuation objectives using a power mean with p=-1.0 (harmonic mean).
# The agent must balance both objectives, with neither being severely sacrificed.
@tf.function
def pendulum_composer(q_values, p_batch=0, p_objectives=-4.0):
    qs_batch = tf.transpose(q_values)
    angle = qs_batch[0]**2.0
    actuation = qs_batch[1]
    q_c = p_mean(p_mean([angle, actuation], p=p_objectives, axis=0), p=p_batch, axis=0)
    return p_mean([angle, actuation], p=p_batch, axis=0), q_c

def are_bodies_in_contact(world, body1, body2):
    # Get the contact list from the world
    for contact in world.contacts:
        # Check if the contact involves both bodies
        if (contact.fixtureA.body == body1 and contact.fixtureB.body == body2) or \
           (contact.fixtureA.body == body2 and contact.fixtureB.body == body1):
            # Ensure the contact is actually touching
            if contact.touching:
                return True
    return False

def lunar_lander_rw(transition: Transition, env: LunarLander)  -> np.ndarray:
    speed = transition.next_state[2:4] / env.observation_space.high[2:4]
    legs_contact = transition.next_state[-2:]
    fuel_cost_bottom = 1.0 - ((transition.action[0]+1.0)/2.0)
    fuel_cost_lr = 1.0 - np.abs(transition.action[1])
    nearness = (1.0 - np.clip(
        np.linalg.norm(transition.next_state[0:2]), 0, 1)
    )
    very_nearness = (1.0 - np.clip(
        2*np.linalg.norm(transition.next_state[0:2]), 0.0, 1.0
    ))**2.0
    # land_stop = p_mean([(legs_contact[0] or legs_contact[1])*1.0, fuel_cost], p=0.0)
    # legs = p_mean(np.concatenate([legs_contact, [fuel_cost_bottom, fuel_cost_lr]]), p=0.5)
    legs = p_mean(legs_contact, p=0.1)
    fuel_cost = p_mean([fuel_cost_lr, fuel_cost_bottom], p=0.5, dtype=tf.float32)
    landed = p_mean([legs, fuel_cost, tf.cast(very_nearness, tf.float32)], p=0.0, dtype=tf.float32)
    # return np.concatenate([[nearness**4.0, very_nearness**2.0], fuel_costs, legs])
    # return np.concatenate([[nearness, very_nearness, fuel_cost_lr, fuel_cost_bottom], legs])
    return np.array([nearness, very_nearness, fuel_cost_lr, fuel_cost_bottom, legs, landed])

@tf.function
def clip_objectives(qs_c):
    nearness=tf.clip_by_value(qs_c[0]/0.8, 0.0, 1.0)
    very_nearness=offset(tf.clip_by_value(qs_c[1]/0.6, 0.0, 1.0), 0.1)
    fuel_cost = offset(tf.clip_by_value(p_mean(qs_c[2:4], p=1.0, axis=0)/0.7, 0.0, 1.0), 0.5)
    legs_touch = offset(tf.clip_by_value(qs_c[4]/0.6, 0.0, 1.0), 0.1)
    landed = offset(tf.clip_by_value(qs_c[5]/0.7, 0.0, 1.0), 0.1)
    return (nearness, very_nearness, legs_touch, fuel_cost, landed)


@tf.function
def lander_composer(q_values, p_batch=0, p_objectives=-4.0):
    q_x_batch = tf.transpose(q_values)
    # qs_c = p_mean(q_values, p=p_batch, axis=0)
    clipped = clip_objectives(q_x_batch)
    # (nearness, very_nearness, legs_touch, fuel_cost, landed) = clipped
    combined_batch = p_mean(clipped, p=p_objectives, axis=0)
    q_c = p_mean(combined_batch, p=p_batch, axis=0)
    qs_c = p_mean(clipped, p=p_batch, axis=1)
    # q_c = p_mean([nearness, very_nearness, legs_touch, fuel_cost, landed], p=p_objectives)
    return qs_c, q_c

@tf.function
def lander_composer2(q_values, p_batch=0, p_objectives=-4.0):
    qs_c = p_mean(q_values, p=p_batch, axis=0)
    (nearness, very_nearness, legs_touch, fuel_cost) = clip_objectives(qs_c)
    q_c = p_mean([nearness, very_nearness, legs_touch, fuel_cost], p=p_objectives)
    return tf.concat([qs_c, [nearness, very_nearness, legs_touch]],axis=0), q_c