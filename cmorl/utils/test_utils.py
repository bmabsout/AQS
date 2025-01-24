from collections import deque
import glob
from cmorl.configs import ForcedTimeLimit
from cmorl.rl_algs.ddpg.ddpg import add_noise_to_weights
from cmorl.utils import save_utils
import numpy as np
import tensorflow as tf

from cmorl.utils.reward_utils import (
    CMORL,
    Transition,
    discounted_window,
    estimated_value_fn,
    values,
)
import multiprocess as mp


def test(
    actor,
    critic,
    env,
    seed=123,
    render=True,
    force_truncate_at=None,
    cmorl=None,
    max_ep_len=None,
    gamma=0.99,
):
    if force_truncate_at is not None:
        env = ForcedTimeLimit(env, max_episode_steps=force_truncate_at)
    o, _ = env.reset(seed=seed)
    np_random = np.random.default_rng(seed)
    os = deque()
    rs = deque()
    cmorl_rs = deque()
    actions = deque()
    while True:
        action = actor(o, np_random)
        # print(action)
        actions.append(action)
        # print(o)
        os.append(o)
        o2, r, d, t, i = env.step(action)
        rs.append(r)
        if cmorl:
            transition = Transition(o, action, o2, d, i)
            cmorl_r = cmorl(transition, env)
            cmorl_rs.append(cmorl_r)
        if d or t or max_ep_len == len(os):
            print(f"ep_len: {len(os)}", "done" if d else "truncated")
            break
        o = o2
        if render:
            env.render()
            # print(f"action: {action}")
            # print(f"o: {o}")
            # print(f"r: {r}")
            if cmorl:
                qs, q_c = cmorl.q_composer([cmorl_r])
                print(f"cmorl_qs: {(q_c.numpy(), qs.numpy())}")
    actions = np.array(actions)
    rs = np.array(rs)
    os = np.array(os)
    cmorl_rs = np.array(cmorl_rs)
    qs = np.array(critic(os, actions))
    np.set_printoptions(precision=2)
    rsum = np.sum(rs)
    print(f"reward: {rsum:.2f}, cmorl: {np.sum(cmorl_rs, axis=0)}")
    estimated_value = estimated_value_fn(cmorl_rs, gamma, done=d)
    # print(f"estimated value:", estimated_value)
    vals = values(cmorl_rs, gamma, done=d)
    offness = np.mean(np.abs(qs - vals), axis=0)
    vals_and_errors = " ".join(
        [f"{val:.2f}+{error:.2f}" for val, error in zip(estimated_value, offness)]
    )
    print("vals+err:", vals_and_errors)
    qs_c, q_c = cmorl.q_composer(vals)
    print("q_c:", np.asarray(q_c).round(2), "qs_c:", np.asarray(qs_c).round(2))
    # print("first:", qs[0], np.sum(discounted_window(rs, gamma, done=d,axis=0)))
    # print("last:", qs[-1])
    # print("max:", np.max(qs, axis=0))
    # print("min:", np.min(qs, axis=0))
    return os, rs, cmorl_rs, rsum, vals


def folder_to_results(
    env,
    render,
    num_tests,
    folder_path,
    force_truncate_at=None,
    cmorl=None,
    max_ep_len=None,
    act_noise=0.0,
    **kwargs,
):
    saved_actor = save_utils.load_actor(folder_path)
    saved_critic = save_utils.load_critic(folder_path)

    def actor(x, np_random):
        return add_noise_to_weights(
            x, saved_actor, env.action_space, act_noise, np_random
        )

    def critic(o, a):
        return saved_critic(np.hstack([o, a], dtype=np.float32))

    runs = [
        test(
            actor,
            critic,
            env,
            seed=17 + i,
            render=render,
            force_truncate_at=force_truncate_at,
            cmorl=cmorl,
            max_ep_len=max_ep_len,
        )
        for i in range(num_tests)
    ]
    return runs


def run_tests(env, cmd_args, folders, cmorl: CMORL = None, max_ep_len=None):
    # a deque so we can effiently append
    q_cs = deque()
    qs_cs = deque()
    rsums_means = deque()
    for folder in folders:
        print("using folder:", folder)
        _, _, _, rsums, valss = zip(
            *folder_to_results(
                env,
                folder_path=folder,
                cmorl=cmorl,
                max_ep_len=max_ep_len,
                **vars(cmd_args),
            )
        )
        qs_c, q_c = cmorl.q_composer(np.concatenate(valss, axis=0))
        q_cs.append(q_c.numpy())
        qs_cs.append(qs_c.numpy())
        rsums_means.append(np.mean(rsums))

    results = {
        "q_c": (np.mean(q_cs, axis=0), np.std(q_cs, axis=0)),
        "qs_c": (np.mean(qs_cs, axis=0), np.std(qs_cs, axis=0)),
        "rsums": (np.mean(rsums_means), np.std(rsums_means)),
    }

    return results


def folder_groups_from_globs(*globs: str):
    folder_groups = {}
    for unglobbed in globs:
        latest_folders = map(save_utils.latest_train_folder, glob.glob(unglobbed))
        folder_groups[unglobbed] = [
            folder for folder in latest_folders if folder is not None
        ]
    return folder_groups


def run_folder_group_tests(env, cmd_args, folder_groups, cmorl=None, max_ep_len=None):
    group_results = {}

    def run_folder_group(folder_group_name, folders):
        print("using folder group:", folder_group_name)
        run_stats = run_tests(
            env, cmd_args, folders=folders, cmorl=cmorl, max_ep_len=max_ep_len
        )
        return folder_group_name, run_stats

    if cmd_args.render:
        results = [
            run_folder_group(folder_group_name, folders)
            for folder_group_name, folders in folder_groups.items()
        ]
    else:
        with mp.Pool(processes=10) as pool:
            results = pool.starmap(run_folder_group, folder_groups.items())

    group_results = {
        folder_group_name: run_stats for folder_group_name, run_stats in results
    }
    return group_results


# import gc
# from contextlib import contextmanager
# import tensorflow as tf
# import logging
# import numpy as np
# from functools import lru_cache

# # Configure TensorFlow for performance
# tf.config.experimental_functions_run_eagerly = False
# tf.config.optimizer.set_jit(True)  # Enable XLA optimization


# class ComposerCache:
#     """Cache for composer functions to avoid retracing"""

#     def __init__(self):
#         self._composer_cache = {}

#     @tf.function(reduce_retracing=True)
#     def call_composer(self, composer_fn, inputs):
#         """Cached composer function call with shape consistency"""
#         # Ensure consistent tensor shape
#         # if input is a tensor then do nothing
#         if isinstance(inputs, tf.Tensor):
#             pass
#         else:
#             inputs = tf.convert_to_tensor(inputs, dtype=tf.float64)
#         # Ensure batch dimension
#         if len(inputs.shape) == 1:
#             inputs = tf.expand_dims(inputs, 0)
#         return composer_fn(inputs)

#     def get_cached_composer(self, composer_fn, input_shape):
#         """Get or create cached composer function"""
#         cache_key = (composer_fn, tuple(input_shape))
#         if cache_key not in self._composer_cache:
#             self._composer_cache[cache_key] = self.call_composer
#         return self._composer_cache[cache_key]


# # Global caches
# composer_cache = ComposerCache()
# model_cache = {}


# def get_cached_model(path):
#     """Get or load model with caching"""
#     if path not in model_cache:
#         model_cache[path] = save_utils.load_actor(path)
#     return model_cache[path]


# @contextmanager
# def model_context():
#     """Context manager for safely handling model resources"""
#     try:
#         yield
#     finally:
#         cleanup_memory()


# def cleanup_memory():
#     """Clean up memory and TensorFlow resources"""
#     try:
#         tf.keras.backend.clear_session()
#         gc.collect()
#     except Exception as e:
#         logging.debug(f"Non-critical cleanup error: {e}")


# def folder_to_results(
#     env,
#     render,
#     num_tests,
#     folder_path,
#     force_truncate_at=None,
#     cmorl=None,
#     max_ep_len=None,
#     act_noise=0.0,
#     **kwargs,
# ):
#     results = []

#     with model_context():
#         saved_actor = get_cached_model(folder_path)
#         saved_critic = save_utils.load_critic(folder_path)

#         def actor(x, np_random):
#             return add_noise_to_weights(
#                 x, saved_actor, env.action_space, act_noise, np_random
#             )

#         def critic(o, a):
#             return saved_critic(np.hstack([o, a], dtype=np.float32))

#         for i in range(num_tests):
#             with model_context():
#                 run_result = test(
#                     actor,
#                     critic,
#                     env,
#                     seed=17 + i,
#                     render=render,
#                     force_truncate_at=force_truncate_at,
#                     cmorl=cmorl,
#                     max_ep_len=max_ep_len,
#                 )
#                 results.append(run_result)

#     return results


# def run_tests(env, cmd_args, folders, cmorl=None, max_ep_len=None):
#     q_cs = []
#     qs_cs = []
#     rsums_means = []

#     for folder in folders:
#         print("using folder:", folder)
#         with model_context():
#             _, _, _, rsums, valss = zip(
#                 *folder_to_results(
#                     env,
#                     folder_path=folder,
#                     cmorl=cmorl,
#                     max_ep_len=max_ep_len,
#                     **vars(cmd_args),
#                 )
#             )

#             # Process values with cached composer
#             values = np.concatenate(valss, axis=0)
#             cached_composer = composer_cache.get_cached_composer(
#                 cmorl.q_composer, values.shape
#             )
#             qs_c, q_c = cached_composer(cmorl.q_composer, values)

#             q_cs.append(q_c.numpy())
#             qs_cs.append(qs_c.numpy())
#             rsums_means.append(np.mean(rsums))

#             del values, valss, rsums
#             gc.collect()

#     results = {
#         "q_c": (np.mean(q_cs, axis=0), np.std(q_cs, axis=0)),
#         "qs_c": (np.mean(qs_cs, axis=0), np.std(qs_cs, axis=0)),
#         "rsums": (np.mean(rsums_means), np.std(rsums_means)),
#     }

#     return results


# def run_folder_group_tests(env, cmd_args, folder_groups, cmorl=None, max_ep_len=None):
#     def run_folder_group(folder_group_name, folders):
#         print("using folder group:", folder_group_name)
#         with model_context():
#             run_stats = run_tests(
#                 env, cmd_args, folders=folders, cmorl=cmorl, max_ep_len=max_ep_len
#             )
#             return folder_group_name, run_stats

#     if cmd_args.render:
#         results = []
#         for folder_group_name, folders in folder_groups.items():
#             result = run_folder_group(folder_group_name, folders)
#             results.append(result)
#     else:
#         # Limit processes to avoid memory issues
#         n_processes = min(3, mp.cpu_count())
#         with mp.Pool(processes=n_processes) as pool:
#             results = pool.starmap(run_folder_group, folder_groups.items())

#     # Final cleanup
#     model_cache.clear()
#     gc.collect()

#     return {folder_group_name: run_stats for folder_group_name, run_stats in results}
