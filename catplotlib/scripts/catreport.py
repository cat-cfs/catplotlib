import logging
import os
import sys
from distutils.dir_util import copy_tree
from glob import glob
from argparse import ArgumentParser

def copy_and_configure(template, output_path, results_dbs, bounding_box=None, config=None):
    if os.path.isdir(template):
        selected_template = template
    else:
        template_root = os.path.join(sys.prefix, "Tools", "catplotlib", "catreport", "templates")
        selected_template = os.path.join(template_root, template)
        if not os.path.exists(selected_template):
            sys.exit(f"Template '{template}' not found.")

    copy_tree(selected_template, output_path)
    write_config(output_path, results_dbs, bounding_box, config)

def write_config(report_path, results_dbs, bounding_box=None, config=None):
    provider_paths = "{"
    for title, path in results_dbs.items():
        provider_paths += f'\n    r"{title}": r"{os.path.abspath(path)}",'

    for template_file in glob(os.path.join(report_path, "*.md")):
        template_contents = open(template_file, "r").read()
        template_contents = template_contents.replace(
            "%providers", f"provider_paths = {provider_paths}\n}}")

        if bounding_box:
            template_contents = template_contents.replace(
                r"..\..\layers\tiled\bounding_box.tif", bounding_box)

        if config:
            template_contents = template_contents.replace(
                "%config", f"config = {config}" if config else "")

        open(template_file, "w").write(template_contents)

def cli():
    logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(message)s")

    parser = ArgumentParser(description="Create output report.")
    parser.add_argument("report_path", help="Path to generate report in")
    parser.add_argument("results", nargs="+", help="Path(s) to results databases in the format `label:path`, i.e. `My_Simulation:c:\runs\foo.db`")
    parser.add_argument("--template", help="Generate report from specified template", default="basic_gcbm")
    parser.add_argument("--bounding_box", type=os.path.abspath, help="Bounding box to show simulation area")
    parser.add_argument("--config", help="Path to JSON report configuration")
    args = parser.parse_args()

    results_dbs = {
        label: path for (label, path) in (results.split(":", 1) for results in args.results)
    }

    copy_and_configure(
        args.template, args.report_path, results_dbs, args.bounding_box, args.config)

if __name__ == "__main__":
    cli()
