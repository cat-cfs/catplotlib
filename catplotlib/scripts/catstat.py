import logging
import sys
import numpy as np
from pathlib import Path
from argparse import ArgumentParser
from catplotlib.util.stats import calculate_stack_stat
from catplotlib.util.tempfile import TempFileManager

def _try_parse_arg(arg):
    try:
        return float(arg)
    except ValueError:
        pass
    
    try:
        return int(arg)
    except ValueError:
        pass
    
    return arg

def cli():
    TempFileManager.delete_on_exit()

    logging.basicConfig(
        level=logging.INFO, stream=sys.stdout,
        format="%(asctime)s %(message)s", datefmt="%m/%d %H:%M:%S")

    parser = ArgumentParser(
        description="Calculate a per-pixel statistic from a stack of layers onto a single output layer.",
        epilog="Any extra --options are passed along to the selected numpy function."
    )
    
    parser.add_argument("pattern", help="File pattern to process")
    parser.add_argument("output_path", type=Path, help="Path to output tif file")
    parser.add_argument("numpy_fn", help="numpy function to apply")
    parser.add_argument("numpy_args", nargs="*", help="numpy positional args")
    parser.add_argument("--chunk_size", help="Chunk size to use when processing layers", default=5000)
    args, extras = parser.parse_known_args()
    
    numpy_kwargs = {}
    for arg in extras:
        if arg.startswith("--"):
            parser.add_argument(arg)
            numpy_kwargs[arg.split("--")[1]] = None
            
    args = parser.parse_args()
    numpy_args = [_try_parse_arg(arg) for arg in args.numpy_args]
    for numpy_kwarg in numpy_kwargs.keys():
        numpy_kwargs[numpy_kwarg] = _try_parse_arg(getattr(args, numpy_kwarg))
    
    numpy_fn = getattr(np, args.numpy_fn)
    calculate_stack_stat(
        args.pattern, args.output_path, numpy_fn, *numpy_args,
        chunk_size=args.chunk_size, **(numpy_kwargs or {})
    )

if __name__ == "__main__":
    cli()
