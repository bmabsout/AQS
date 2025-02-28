from dataclasses import dataclass, field
from functools import reduce
from pathlib import Path
import time
from argparse import Namespace
import tensorflow as tf

from cmorl.utils.args_utils import Arg_Serializer, Serialized_Argument, namespace_serializer

@dataclass(init=False) # so the type system shows the options
class HyperParams(Namespace):
    ac_kwargs        : dict[str, object]
    prev_folder      : None | Path
    seed             : int
    steps_per_epoch  : int
    epochs           : int
    replay_size      : int
    gamma            : float
    polyak           : float
    pi_lr            : float
    q_lr             : float
    batch_size       : int
    start_steps      : int
    act_noise        : float
    max_ep_len       : int
    train_every      : int
    train_steps      : int
    p_batch          : float
    q_batch          : float
    q_objectives     : float
    p_objectives     : float
    qd_power         : float
    threshold        : float
    before_clip      : float
    env_args         : dict[str, object]
    ignore_aps       : bool
    # noise_schedule : tf.keras.optimizers.schedules.LearningRateSchedule

descriptions: dict[str,  str] = {
    "ac_kwargs": "Any kwargs appropriate for the actor_critic function you provided",
    "prev_folder": "The folder to load the previous model from",
    "seed": "Seed for random number generators",
    "steps_per_epoch": "Number of steps of interaction (state-action pairs) for the agent and the environment in each epoch",
    "epochs": "Number of epochs to run and train agent",
    "replay_size": "Maximum length of replay buffer",
    "gamma": "Discount factor. (Always between 0 and 1)",
    "polyak": "Interpolation factor in polyak averaging for target networks. Target networks are updated towards main networks according to: theta_targ <- rho theta_targ + (1-rho) theta where rho is polyak. (Always between 0 and 1, usually close to 1)",
    "pi_lr": "Learning rate for policy",
    "q_lr": "Learning rate for Q-networks",
    "batch_size": "Minibatch size for SGD",
    "start_steps": "Number of steps for uniform-random action selection, before running real policy. Helps exploration",
    "act_noise": "Stddev for Gaussian exploration noise added to policy at training time. (At test time, no noise is added)",
    "max_ep_len": "Maximum length of an episode",
    "train_every": "Number of steps to wait before training",
    "train_steps": "Number of training steps to take",
    "p_batch": "The p-value for composing the Q-values across the batch",
    "p_objectives": "The p-value for composing the Q-values across the objectives",
    "q_batch": "The p-mean value for critic error's batch",
    "q_objectives": "The p-mean value for composing the different critic's q-value errors",
    "qd_power": "The weight of the td-inf loss",
    "threshold": "The threshold for the loss to keep the actions in range",
    "before_clip": "The loss weight for the clip loss",
    "ignore_aps": "Whether to ignore the APS specification and train on original rewards, ala standard DDPG",
}

abbreviations = {
    "prev_folder": "p",
    "seed": "s",
    "epochs": "e",
    "gamma": "g",
    "p_batch": "p_b",
    "p_objectives": "p_o",
    "q_batch": "q_b",
    "q_objectives": "q_o",
    "qd_power": "q_d"
}

def default_hypers():
    return HyperParams(
        ac_kwargs       = {
            "critic_hidden_sizes": [400, 300],
            "actor_hidden_sizes": [32, 32],
            "actor_keep_in_range": 1e-3,
            "critic_keep_in_range": 1e-3,
        },
        prev_folder     = None,
        seed            = int(time.time() * 1e5) % int(1e6),
        steps_per_epoch = 2000,
        epochs          = 100,
        replay_size     = int(1e5),
        gamma           = 0.99,
        polyak          = 0.99,
        pi_lr           = 3e-3,
        q_lr            = 3e-3,
        batch_size      = 100,
        start_steps     = 1000,
        act_noise       = 0.05,
        max_ep_len      = None,
        train_every     = 50,
        train_steps     = 50,
        p_batch         = 1.0,
        p_objectives    = -1.0,
        q_batch         = 1.0,
        q_objectives    = 1.0,
        qd_power        = 1.0,
        before_clip     = 1e-2,
        threshold       = 1.0,
        env_args        = {},
        ignore_aps      = False,
    )

def combine(*hps: HyperParams):
    """Combine multiple hyperparams objects into one. The later objects override the earlier ones."""
    return reduce(lambda x, y: HyperParams(**{**vars(x), **vars(y)}), hps, HyperParams())


def rl_alg_serializer(experiment_name=None):
    return Arg_Serializer(
        Serialized_Argument(
            name="experiment_name",
            abbrev="n",
            type=str,
            required=True if experiment_name is None else False,
            default=experiment_name,
            help="name of the experiment"
        ),
        ignored={"experiment_name"},
    )


def default_serializer(hypers=HyperParams(), experiment_name=None):
    combined_hypers = combine(default_hypers(), hypers)
    return Arg_Serializer.join(
        namespace_serializer(combined_hypers, ignored={"seed"}, descriptions=descriptions, abbrevs=abbreviations),
        rl_alg_serializer(experiment_name=experiment_name),
    )
