from cmorl.rl_algs.ddpg.ddpg import ddpg, HyperParams
from cmorl.utils import args_utils
from Pendulum import PendulumEnv
import Pendulum


def parse_args_and_train(args=None, p_values_list=[0, -4, 0, -4]):
    import cmorl.utils.train_utils as train_utils
    import cmorl.utils.args_utils as args_utils

    serializer = args_utils.default_serializer(epochs=8, learning_rate=1e-4)
    cmd_args = args_utils.parse_arguments(serializer)
    hp = HyperParams(
        start_steps=2000,
        epochs=cmd_args.epochs,
        q_lr=cmd_args.learning_rate,
        pi_lr=cmd_args.learning_rate,
        seed=cmd_args.seed,
        max_ep_len=200,
        steps_per_epoch=5000,
        p_loss_batch=p_values_list[0],
        p_loss_objectives=p_values_list[1],
        p_Q_batch=p_values_list[2],
        p_Q_objectives=p_values_list[3],
    )
    generated_params = train_utils.create_train_folder_and_params(
        "Pendulum-custom", hp, cmd_args, serializer
    )
    env_fn = lambda: PendulumEnv(
        g=10.0, setpoint=0.0, reward_fn=Pendulum.multi_dim_reward
    )
    ddpg(
        env_fn,
        experiment_description="Testing the variance with resect to p-value when composing Q-values.",
        **generated_params,
    )


if __name__ == "__main__":
    import itertools

    p_values = range(-50, 51, 2)
    # train every possible p-value combination of 4 values from p_values
    p_values_list = list(itertools.product(p_values, repeat=4))
    print(f"Training {len(p_values_list)} different p-value combinations.")
    for p_values in p_values_list:
        parse_args_and_train(p_values_list=p_values)