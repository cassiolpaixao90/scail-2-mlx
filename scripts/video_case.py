"""Manage exercise cases without loading models, downloading weights or generating video."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scail2_mlx.utils.cases import initialize, record, review_template, evaluate, read, write_new


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    init = commands.add_parser('init')
    init.add_argument('--case', required=True)
    init.add_argument('--source', required=True)
    init.add_argument('--reference', required=True)
    init.add_argument('--name', required=True)
    rec = commands.add_parser('record')
    rec.add_argument('--case', required=True)
    rec.add_argument('--run', required=True)
    rec.add_argument('--stage', choices=['smoke', 'preview', 'final'], required=True)
    rec.add_argument('--candidate', required=True)
    rec.add_argument('--settings', required=True)
    template = commands.add_parser('review-template')
    validate = commands.add_parser('validate')
    for sub in (template, validate):
        sub.add_argument('--case', required=True)
        sub.add_argument('--run', required=True)
        sub.add_argument('--output', required=True)
    validate.add_argument('--review')
    validate.add_argument('--require-delivery', action='store_true',
                          help='Exit with code 2 unless the final candidate is eligible for delivery')
    args = parser.parse_args()
    if args.command == 'init':
        result = initialize(args.case, args.source, args.reference, args.name)
    elif args.command == 'record':
        result = record(args.case, args.run, args.stage, args.candidate, read(args.settings))
    elif args.command == 'review-template':
        result = review_template(args.case, args.run)
        write_new(args.output, result)
    else:
        result = evaluate(args.case, args.run, read(args.review) if args.review else None)
        write_new(args.output, result)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if args.command == 'validate' and args.require_delivery and not result['eligible_for_delivery']:
        raise SystemExit(2)


if __name__ == '__main__':
    main()
