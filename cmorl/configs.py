from functools import partial
from typing import Callable

import gymnasium
import gymnasium.wrappers

from cmorl.rl_algs.ddpg.hyperparams import HyperParams
from cmorl.utils.reward_utils import CMORL, default_q_composer
from cmorl import reward_fns

class Config:
    def __init__(self, cmorl: CMORL | None = None, hypers: HyperParams = HyperParams(), wrapper = gymnasium.Wrapper):
        self.cmorl = cmorl
        self.hypers = hypers
        self.wrapper = wrapper

class FixSleepingLander(gymnasium.Wrapper):
    def step(self, action):
        obs, reward, done, truncated, info = self.env.step(action)
        if not self.env.lander.awake:
            truncated = True
            done = False
        return obs, reward, done, truncated, info
    
class ForcedTimeLimit(gymnasium.wrappers.TimeLimit):
    def step(self, action):
        obs, reward, done, _, info = super().step(action)
        truncated = self._elapsed_steps >= self._max_episode_steps
        return obs, reward, done, truncated, info

env_configs: dict[str, Config] = {
    "Reacher-v4": Config(
        CMORL(reward_fns.multi_dim_reacher),
        HyperParams(
            ac_kwargs={
                "obs_normalizer": [1.0, 1.0, 1.0, 1.0, 2.0, 2.0, 4.0, 4.0, 2.0, 2.0, 2.0],
            },
        ),
        wrapper=partial(ForcedTimeLimit, max_episode_steps=100),
    ),
    "Ant-v4": Config(
        CMORL(partial(reward_fns.mujoco_multi_dim_reward_joints_x_velocity)),
        HyperParams(pi_lr=1e-3, q_lr=1e-3, env_args={"use_contact_forces": True}, epochs=100, ac_kwargs={"critic_hidden_sizes": (512, 512), "actor_hidden_sizes": (64, 64)}),
    ),
    "Hopper-v4": Config(
        CMORL(partial(reward_fns.mujoco_multi_dim_reward_joints_x_velocity, speed_multiplier=2.0)),
        HyperParams(gamma=0.99, pi_lr=1e-3, q_lr=1e-3, epochs=60),
    ),
    "HalfCheetah-v4": Config(
        CMORL(partial(reward_fns.mujoco_multi_dim_reward_joints_x_velocity, speed_multiplier=0.15)),
        HyperParams(gamma=0.99, epochs=200, pi_lr=1e-3, q_lr=1e-3),
    ),
    "Pendulum-v1": Config(
        CMORL(partial(reward_fns.multi_dim_pendulum, setpoint=0.0))
    ),
    "LunarLanderContinuous-v2": Config(
        CMORL(reward_fns.lunar_lander_rw, reward_fns.lander_composer),
        HyperParams(
            ac_kwargs={
                "obs_normalizer": gymnasium.make("LunarLanderContinuous-v2").observation_space.high, # type: ignore
                "critic_hidden_sizes": (128, 128,128),
                "actor_hidden_sizes": (32, 32),
            },
            gamma=0.99,
            max_ep_len=400,
            epochs=40,
            # p_objectives = 0.5,
            # p_batch = 2.0,
        ),
        wrapper=FixSleepingLander,
    ),
}

def get_env_and_config(env_name: str) -> tuple[Callable[..., gymnasium.Env], Config]:
    config = env_configs.get(env_name, Config())
    make_env = lambda **kwargs: config.wrapper(gymnasium.make(env_name, **{**kwargs, **config.hypers.env_args}))
    return make_env, config 