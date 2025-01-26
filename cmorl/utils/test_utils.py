from collections import deque
import glob
from cmorl.configs import ForcedTimeLimit
from cmorl.rl_algs.ddpg.ddpg import add_noise_to_weights
from cmorl.utils import save_utils
import numpy as np
import tensorflow as tf
from multiprocess import Queue, Value
import signal
import os
from functools import partial
import time
from datetime import datetime, timedelta
import threading

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
            # print(f"ep_len: {len(os)}", "done" if d else "truncated")
            break
        o = o2
        if render:
            env.render()
            # print(f"action: {action}")
            # print(f"o: {o}")
            # print(f"r: {r}")
            if cmorl:
                qs, q_c = cmorl.q_composer([cmorl_r])
                # print(f"cmorl_qs: {(q_c.numpy(), qs.numpy())}")
    actions = np.array(actions)
    rs = np.array(rs)
    os = np.array(os)
    cmorl_rs = np.array(cmorl_rs)
    qs = np.array(critic(os, actions))
    np.set_printoptions(precision=2)
    rsum = np.sum(rs)
    # print(f"reward: {rsum:.2f}, cmorl: {np.sum(cmorl_rs, axis=0)}")
    estimated_value = estimated_value_fn(cmorl_rs, gamma, done=d)
    # print(f"estimated value:", estimated_value)
    vals = values(cmorl_rs, gamma, done=d)
    offness = np.mean(np.abs(qs - vals), axis=0)
    vals_and_errors = " ".join(
        [f"{val:.2f}+{error:.2f}" for val, error in zip(estimated_value, offness)]
    )
    # print("vals+err:", vals_and_errors)
    qs_c, q_c = cmorl.q_composer(vals)
    # print("q_c:", np.asarray(q_c).round(2), "qs_c:", np.asarray(qs_c).round(2))
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


# def run_folder_group_tests(env, cmd_args, folder_groups, cmorl=None, max_ep_len=None):
#     group_results = {}

#     def run_folder_group(folder_group_name, folders):
#         print("using folder group:", folder_group_name)
#         run_stats = run_tests(
#             env, cmd_args, folders=folders, cmorl=cmorl, max_ep_len=max_ep_len
#         )
#         return folder_group_name, run_stats

#     if cmd_args.render:
#         results = [
#             run_folder_group(folder_group_name, folders)
#             for folder_group_name, folders in folder_groups.items()
#         ]
#     else:
#         with mp.Pool(processes=30) as pool:
#             results = pool.starmap(run_folder_group, folder_groups.items())

#     group_results = {
#         folder_group_name: run_stats for folder_group_name, run_stats in results
#     }
#     return group_results


import multiprocess as mp
import os
import sys
import time
from datetime import datetime
from typing import Dict, List, Tuple, Any


class ProcessManager:
    def __init__(self, max_workers: int = None):
        self.max_workers = max_workers or min(40, mp.cpu_count())
        self.counter = mp.Value("i", 0)
        self.result_queue = mp.Queue()

    def _worker_process(
        self,
        task_id: int,
        func: callable,
        args: tuple,
        counter: mp.Value,
        result_queue: mp.Queue,
    ):
        try:
            result = func(*args)
            with counter.get_lock():
                counter.value += 1
            result_queue.put((task_id, result))
        except Exception as e:
            result_queue.put((task_id, None))
            print(f"Error in task {task_id}: {str(e)}")
        finally:
            result_queue.put(("DONE", task_id))

    def _display_progress(self, total: int):
        sys.stdout.write(
            f"\n\n\rProgress: {self.counter.value}/{total} tasks completed\n\n"
        )
        sys.stdout.flush()

    def run_parallel(self, func: callable, items: List[Tuple]) -> List[Any]:
        total_tasks = len(items)
        results = {}
        completed_tasks = set()

        processes = []
        for i, args in enumerate(items):
            if not isinstance(args, tuple):
                args = (args,)
            p = mp.Process(
                target=self._worker_process,
                args=(i, func, args, self.counter, self.result_queue),
            )
            processes.append(p)

        # Start initial batch of processes
        active_processes = processes[: self.max_workers]
        next_process_idx = self.max_workers

        for p in active_processes:
            p.start()

        while len(completed_tasks) < total_tasks:
            msg_type, data = self.result_queue.get()

            if msg_type == "DONE":
                task_id = data
                completed_tasks.add(task_id)

                # Start next process if any remaining
                if next_process_idx < len(processes):
                    processes[next_process_idx].start()
                    next_process_idx += 1
            else:
                task_id, result = msg_type, data
                results[task_id] = result

            self._display_progress(total_tasks)

        # Clean up
        for p in processes:
            p.join()

        print("\nCompleted all tasks!")
        return [results.get(i) for i in range(total_tasks)]


def run_folder_group_tests(env, cmd_args, folder_groups, cmorl=None, max_ep_len=None):
    def run_folder_group(
        folder_group_name: str, folders: List[str]
    ) -> Tuple[str, Dict]:
        print(f"\nTesting group: {folder_group_name}")
        run_stats = run_tests(
            env, cmd_args, folders=folders, cmorl=cmorl, max_ep_len=max_ep_len
        )
        return (folder_group_name, run_stats)

    if cmd_args.render:
        results = [
            run_folder_group(folder_group_name, folders)
            for folder_group_name, folders in folder_groups.items()
        ]
    else:
        process_mgr = ProcessManager()
        results = process_mgr.run_parallel(
            run_folder_group,
            [(name, folders) for name, folders in folder_groups.items()],
        )
        # Filter out None results
        results = [r for r in results if r is not None]

    return dict(results)
