from functools import partial
from typing import Callable

import gymnasium
from gymnasium.wrappers.time_limit import TimeLimit
import numpy as np

from cmorl.rl_algs.ddpg.hyperparams import HyperParams, combine, default_hypers
from cmorl.utils.reward_utils import CMORL, perf_schedule
from cmorl import reward_fns
from envs import Boids

class Config:
    def __init__(self, cmorl: CMORL | None = None, hypers: HyperParams = HyperParams(), wrapper = gymnasium.Wrapper):
        self.cmorl = cmorl
        self.hypers = combine(default_hypers(), hypers)
        self.wrapper = wrapper

class FixLander(gymnasium.Wrapper):
    def are_bodies_in_contact(self, body1, body2):
        # Get the contact list from the world
        for contact in self.env.world.contacts:
            # Check if the contact involves both bodies
            if (contact.fixtureA.body == body1 and contact.fixtureB.body == body2) or \
               (contact.fixtureA.body == body2 and contact.fixtureB.body == body1):
                # Ensure the contact is actually touching
                if contact.touching:
                    return True
        return False

    def step(self, action):
        obs, reward, done, truncated, info = self.env.step(action)
        legs_contact = np.array([self.are_bodies_in_contact(leg, self.env.moon) for leg in self.env.legs]) # hack because the contacts don't work when the legs are asleep which affects our landed objective
        obs[-2:] = legs_contact
        if not self.env.lander.awake:
            truncated = True
            done = False
        return obs, reward, done, truncated, info
    
class ForcedTimeLimit(TimeLimit):
    def step(self, action):
        obs, reward, done, _, info = super().step(action)
        truncated = self._elapsed_steps >= self._max_episode_steps
        return obs, reward, done, truncated, info

env_configs: dict[str, Config] = {
    "Reacher-v4": Config(
        reward_fns.reacher_cmorl,
        HyperParams(
            ac_kwargs={
                "obs_normalizer": [1.0, 1.0, 1.0, 1.0, 2.0, 2.0, 4.0, 4.0, 2.0, 2.0, 2.0],
            },
            steps_per_epoch=2000,
            gamma = 0.9,
            polyak = 0.9,
            replay_size = 10000,
            qd_power = 0.5,
            p_batch = 0.5,
            start_steps = 400,
            act_noise = 0.01,
            p_objectives = -2.0,
            threshold = 2.0,
            # before_clip = 1.0
        ),
        # wrapper=partial(ForcedTimeLimit, max_episode_steps=200),
    ),
    "Ant-v4": Config(
        reward_fns.mujoco_CMORL(num_actions=8, speed_multiplier=0.5),
        HyperParams(env_args={"use_contact_forces": True}, epochs=100, act_noise=0.05, steps_per_epoch=2000),
    ),
    "Hopper-v4": Config(
        reward_fns.mujoco_CMORL(num_actions=3, speed_multiplier=0.5),
        # None,
        HyperParams(
            ac_kwargs = {
                "critic_hidden_sizes": [400, 300],
            #     "critic_hidden_sizes": [512, 512],
                "actor_hidden_sizes": [32,32],
            },
            epochs=20,
            steps_per_epoch=2000,
            p_objectives=-1.0,
            act_noise = 0.07,
            threshold=1.5,
            qd_power=0.75,
            # pi_lr=3e-4,
            # q_lr=3e-4,
            polyak=0.9,
            start_steps=2000,
            # replay_size=5000,
        ),
    ),
    "Walker2d-v4": Config(
        reward_fns.walker_CMORL(speed_multiplier=0.3),
        # None,
        HyperParams(
            ac_kwargs = {
                "critic_hidden_sizes": [400, 300],
            #     "critic_hidden_sizes": [512, 512],
                "actor_hidden_sizes": [32,32],
            },
            epochs=20,
            steps_per_epoch=2000,
            p_objectives=0.0,
            before_clip = 0.1,
            act_noise = 0.02,
            threshold=0.2,
        ),
    ),
    "HalfCheetah-v4": Config(
        # reward_fns.mujoco_CMORL(num_actions=6, speed_multiplier=0.25),
        reward_fns.halfcheetah_CMORL(),

        HyperParams(epochs=200, act_noise=0.05, p_objectives=-1.0,
            ac_kwargs={
                "critic_hidden_sizes": [400, 300],
                "actor_hidden_sizes": [32, 32],
            },
            qd_power=1.0,
            before_clip=0.1,
            steps_per_epoch=2000,
            # pi_lr=3e-4,
            # threshold = 0.5
        ),
    ),
    "Pendulum-v1": Config(
        CMORL(partial(reward_fns.multi_dim_pendulum, setpoint=0.0)),
        # None,
        HyperParams(
            ac_kwargs = {
                "critic_hidden_sizes": [400, 300],
                "actor_hidden_sizes": [32, 32],
            },
            epochs=250,
            steps_per_epoch=2000,
            pi_lr=3e-3,
            q_lr=3e-3,
            # act_noise=0.1,
            before_clip=0.1,
            p_objectives=0.0,
        )
    ),
    "Pendulum-custom": Config(
        CMORL(partial(reward_fns.multi_dim_pendulum, setpoint=0.0))
    ),
    "LunarLanderContinuous-v2": Config(
        CMORL(reward_fns.lunar_lander_rw, reward_fns.lander_composer),
        HyperParams(
            ac_kwargs={
                "obs_normalizer": gymnasium.make("LunarLanderContinuous-v2").observation_space.high,
                "critic_hidden_sizes": [400, 300],
                "actor_hidden_sizes": [32, 32],
            },
            epochs=250,
            steps_per_epoch=2000,
            
            p_objectives=-1.0,
            act_noise=0.05,
            # pi_lr=1e-3,
            # q_lr = 1e-3,
            p_batch= 1.0,
            start_steps=2000,
            # replay_size=30000,
            polyak=0.9,
            qd_power=0.5,
            threshold=1.5,
            # before_clip = 0.01
        ),
        wrapper=lambda x: TimeLimit(FixLander(x), max_episode_steps=400),
    ),
    "Bittle-custom": Config(
        CMORL(reward_fns.bittle_rw),
        HyperParams(
            max_ep_len=400,
            env_args={"observe_joints": True},
            # qd_power=0.5
        ),
    ),
    "Boids-v0": Config(
        CMORL(Boids.multi_dim_reward, randomization_schedule=perf_schedule),
        HyperParams(
            max_ep_len=400,
        )
    ),
}

def get_env_and_config(env_name: str) -> tuple[Callable[..., gymnasium.Env], Config]:
    config = env_configs.get(env_name, Config())
    make_env = lambda **kwargs: config.wrapper(gymnasium.make(env_name, **{**kwargs, **config.hypers.env_args}))
    return make_env, config 
