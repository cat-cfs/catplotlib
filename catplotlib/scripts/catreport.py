import logging
import os
import sys
import shutil
from glob import glob
from argparse import ArgumentParser

def copy_and_configure(template, output_path, results_paths):
    template_root = os.path.join(sys.prefix, "Tools", "catplotlib", "catreport", "templates")
    selected_template = os.path.join(template_root, template)
    if not os.path.exists(selected_template):
        sys.exit(f"Template '{template}' not found.")

    provider_paths = "{"
    for results in results_paths:
        label, path = results.split(":", 1)
        provider_paths += f'\n    r"{label}": r"{os.path.abspath(path)}",'

    shutil.copytree(selected_template, output_path)
    for template_file in glob(os.path.join(output_path, "*.md")):
        template_contents = open(template_file, "r").read().replace(
            "%providers", f"provider_paths = {provider_paths}\n}}")

        open(template_file, "w").write(template_contents)

def cli():
    logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(message)s")

    parser = ArgumentParser(description="Create output report")
    parser.add_argument("report_path", help="Path to generate report in")
    parser.add_argument("results", nargs="+", help="Path(s) to results databases in the format `label:path`, i.e. `My_Simulation:c:\runs\foo.db`")
    parser.add_argument("--template", help="Generate report from specified template", default="basic_gcbm")
    args = parser.parse_args()

    copy_and_configure(args.template, args.report_path, args.results)

if __name__ == "__main__":
    cli()
