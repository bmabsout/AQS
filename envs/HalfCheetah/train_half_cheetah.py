from cmorl.rl_algs.ddpg.ddpg import ddpg, HyperParams
from cmorl.utils import args_utils
from half_cheetah import HalfCheetahEnv
import half_cheetah


def parse_args_and_train(args=None):
    import cmorl.utils.train_utils as train_utils
    import cmorl.utils.args_utils as args_utils

    serializer = args_utils.default_serializer(epochs=2, learning_rate=1e-4)
    cmd_args = args_utils.parse_arguments(serializer)
    hp = HyperParams(
        epochs=cmd_args.epochs,
        q_lr=cmd_args.learning_rate,
        pi_lr=cmd_args.learning_rate,
        seed=cmd_args.seed,
        max_ep_len=200,
    )
    generated_params = train_utils.create_train_folder_and_params(
        "Pendulum-custom", hp, cmd_args, serializer
    )
    env_fn = lambda: HalfCheetahEnv(
        reward_fn=half_cheetah.multi_dim_reward,
        # render_mode="human",
    )
    ddpg(env_fn, **generated_params)


if __name__ == "__main__":
    parse_args_and_train()
