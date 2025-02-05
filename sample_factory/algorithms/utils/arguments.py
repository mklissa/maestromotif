import argparse
import copy
import json
import os
import sys

from sample_factory.algorithms.utils.evaluation_config import add_eval_args
from sample_factory.envs.env_config import add_env_args, env_override_defaults
from sample_factory.utils.utils import (
    AttrDict,
    cfg_file,
    get_git_commit_hash,
    log,
    str2bool,
)


def get_algo_class(algo):
    algo_class = None

    if algo == 'APPO':
        from sample_factory.algorithms.appo.appo import APPO
        algo_class = APPO
    elif algo == 'DUMMY_SAMPLER':
        from sample_factory.algorithms.dummy_sampler.sampler import DummySampler
        algo_class = DummySampler
    else:
        log.warning('Algorithm %s is not supported', algo)

    return algo_class


def arg_parser(argv=None, evaluation=False):
    if argv is None:
        argv = sys.argv[1:]

    # noinspection PyTypeChecker
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter, add_help=False)

    # common args
    parser.add_argument('--algo', type=str, default='APPO', required=False, help='Algo type to use (pass "APPO" if in doubt)')
    parser.add_argument('--env', type=str, default='nle_all_but_engrave', required=False, help='Fully-qualified environment name in the form envfamily_envname, e.g. atari_breakout or doom_battle')
    parser.add_argument('--evaluation', type=str2bool, default=False, help='Evaluate the algorithm or not')
    parser.add_argument('--eval_target', type=str, default='none', help='Evaluate the algorithm or not')
    parser.add_argument('--code_seed', type=int, default=-1, help='Evaluate the algorithm or not')

    # Environment args
    parser.add_argument('--root_env', type=str, default='NetHackScoreMonk-v1', required=False, help='Fully-qualified environment name in the form envfamily_envname, e.g. atari_breakout or doom_battle')
    parser.add_argument("--max_episode_steps", default=10_000, type=int, help="The max number of steps to unroll episodes.")
    parser.add_argument('--get_stats', type=str2bool, default=False, help='To run the algo only for collecting statistics')

    # Wandb args
    parser.add_argument('--wandb', type=str2bool, default=False, help='To log or not on wandb')
    parser.add_argument('--wandb_project', type=str, default='maestromotif', help='The project under which to save wandb runs')
    parser.add_argument('--wandb_entity', type=str, default='entity', help='The wandb entity owning the project.')
    parser.add_argument('--wandb_dir', type=str, default=None, help='The local directory where we save wandb data.')
    parser.add_argument('--wandb_group', type=str, default=None, help='The group name for wandb logging.')

    # Intrinsic reward args
    parser.add_argument('--checkpoint_num', default=0, type=int, help='The checkpoint number to load the reward model from.')
    parser.add_argument('--beta_count_exponent', default=3, type=float, help='The exponent for the counts.')
    parser.add_argument('--eps_threshold_quantile', default="[0.95, 0.85, 0.85, 0.85, 0.85]", type=str, help='Root dir to load reward model from.')
    parser.add_argument('--rew_norm', default=True, type=str2bool, help='To normalize or not the intrinsic reward.')
    parser.add_argument("--reward_encoder", default='nle_torchbeast_encoder', type=str, help="encoder used for the reward function.")
    parser.add_argument("--use_mlp_core", default=False, type=bool, help="To use or not an MLP in the core part of the agent")
    parser.add_argument("--crop_size", default=12, type=int, help="the size of the crop to use in the CDGPT5 baseline.")
    parser.add_argument("--skill_steps", default=1000, type=int, help="How many steps does skill 0 spend on each level")
    parser.add_argument("--num_skills", default=5, type=int, help="How many skills")

    # NLE TorchBeast Encoder args
    parser.add_argument("--encoder_embedding_dim", default=128, type=int, help="embedding dim")
    parser.add_argument("--encoder_hidden_dim", default=512, type=int, help="hidden dim for encoder")
    parser.add_argument("--encoder_final_activ", default='ln', type=str, help="final activation function for encoder")
    parser.add_argument("--encoder_crop_dim", default=16, type=int, help="crop size")
    parser.add_argument("--encoder_num_layers", default=2, type=int, help="number of layers")
    parser.add_argument("--encoder_msg_model", default='lt_cnn', type=str, help="message model")
    parser.add_argument("--use_crop", default=False, type=str2bool, help="To use a cropped view of the glyphs or not")
    parser.add_argument("--use_glyphs", default=False, type=str2bool, help="To use the full glyphs map or not")
    parser.add_argument("--use_blstats", default=False, type=str2bool, help="To use the bl stats or not")
    parser.add_argument("--use_diffstats", default=True, type=str2bool, help="To use the diff stats or not")
    parser.add_argument("--diffstats_size", default=5, type=int, help="The number of stats used in diff")
    parser.add_argument("--diff_h", default=1000, type=int, help="The horizon for diff stats")

    # Message encoder arguments
    parser.add_argument("--encoder_model_msg", default='torchbeast', type=str, help="Type of model for the message encoding")
    parser.add_argument("--encoder_aggregation_mode_msg", default='mean', type=str,
                        help="Type of aggregation for the message encoding")
    parser.add_argument("--encoder_stats_model", default='three_hid_layers', type=str, help="Type of model for the blstats encoding")

    parser.add_argument(
        '--experiment', type=str, default='default_experiment',
        help='Unique experiment name. This will also be the name for the experiment folder in the train dir.'
             'If the experiment folder with this name aleady exists the experiment will be RESUMED!'
             'Any parameters passed from command line that do not match the parameters stored in the experiment cfg.json file will be overridden.',
    )
    parser.add_argument(
        '--experiments_root', type=str, default=None, required=False,
        help='If not None, store experiment data in the specified subfolder of train_dir. Useful for groups of experiments (e.g. gridsearch)',
    )
    parser.add_argument('-h', '--help', action='store_true', help='Print the help message', required=False)

    basic_args, _ = parser.parse_known_args(argv)
    algo = basic_args.algo
    env = basic_args.env

    # algorithm-specific parameters (e.g. for APPO)
    algo_class = get_algo_class(algo)
    algo_class.add_cli_args(parser)

    # env-specific parameters (e.g. for Doom env)
    add_env_args(env, parser)

    if evaluation:
        add_eval_args(parser)

    # env-specific default values for algo parameters (e.g. model size and convolutional head configuration)
    env_override_defaults(env, parser)

    return parser


def parse_args(argv=None, evaluation=False, parser=None):
    if argv is None:
        argv = sys.argv[1:]

    if parser is None:
        parser = arg_parser(argv, evaluation)

    # parse all the arguments (algo, env, and optionally evaluation)
    args = parser.parse_args(argv)
    args = postprocess_args(args, argv, parser)

    return args


def postprocess_args(args, argv, parser):
    """
    Postprocessing after parse_args is called.
    Makes it easy to use SF within another codebase which might have its own parse_args call.

    """

    if args.help:
        parser.print_help()
        sys.exit(0)

    args.command_line = ' '.join(argv)

    # following is the trick to get only the args passed from the command line
    # We copy the parser and set the default value of None for every argument. Since one cannot pass None
    # from command line, we can differentiate between args passed from command line and args that got initialized
    # from their default values. This will allow us later to load missing values from the config file without
    # overriding anything passed from the command line
    no_defaults_parser = copy.deepcopy(parser)
    for arg_name in vars(args).keys():
        no_defaults_parser.set_defaults(**{arg_name: None})
    cli_args = no_defaults_parser.parse_args(argv)

    for arg_name in list(vars(cli_args).keys()):
        if cli_args.__dict__[arg_name] is None:
            del cli_args.__dict__[arg_name]

    args.cli_args = vars(cli_args)
    args.git_hash, args.git_repo_name = get_git_commit_hash()
    return args


def default_cfg(algo='APPO', env='env', experiment='test'):
    """Useful for tests."""
    return parse_args(argv=[f'--algo={algo}', f'--env={env}', f'--experiment={experiment}'])


def load_from_checkpoint(cfg):
    filename = cfg_file(cfg)
    if not os.path.isfile(filename):
        raise Exception(f'Could not load saved parameters for experiment {cfg.experiment}')

    with open(filename, 'r') as json_file:
        json_params = json.load(json_file)
        log.warning('Loading existing experiment configuration from %s', filename)
        loaded_cfg = AttrDict(json_params)

    # override the parameters in config file with values passed from command line
    for key, value in cfg.cli_args.items():
        if key in loaded_cfg and loaded_cfg[key] != value:
            log.debug('Overriding arg %r with value %r passed from command line', key, value)
            loaded_cfg[key] = value

    # incorporate extra CLI parameters that were not present in JSON file
    for key, value in vars(cfg).items():
        if key not in loaded_cfg:
            log.debug('Adding new argument %r=%r that is not in the saved config file!', key, value)
            loaded_cfg[key] = value

    return loaded_cfg


def maybe_load_from_checkpoint(cfg):
    filename = cfg_file(cfg)
    if not os.path.isfile(filename):
        log.warning('Saved parameter configuration for experiment %s not found!', cfg.experiment)
        log.warning('Starting experiment from scratch!')
        return AttrDict(vars(cfg))

    return load_from_checkpoint(cfg)
