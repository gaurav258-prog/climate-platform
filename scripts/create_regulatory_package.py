"""
Regulatory Package CLI — maker/checker workflow.

Commands:
  create   — MAKER: build draft package from canonical scores
  approve  — CHECKER: release package (4-eyes, different user required)
  get      — retrieve any package by ID
  list     — list all packages for a customer

Usage examples:
  # Build an ECB draft for a customer
  python scripts/create_regulatory_package.py create \\
    --customer <uuid> \\
    --framework ECB \\
    --period-start 2024-01-01 --period-end 2024-12-31 \\
    --maker analyst@bank.com

  # Build a CSRD draft
  python scripts/create_regulatory_package.py create \\
    --customer <uuid> \\
    --framework CSRD \\
    --period-start 2024-01-01 --period-end 2024-12-31 \\
    --maker analyst@bank.com \\
    --company "Eurobank AG" \\
    --nace A01 D35

  # Checker approves (must be a different user)
  python scripts/create_regulatory_package.py approve \\
    --package-id <uuid> \\
    --checker riskmanager@bank.com

  # Retrieve a package
  python scripts/create_regulatory_package.py get --package-id <uuid>

  # List packages for a customer
  python scripts/create_regulatory_package.py list --customer <uuid>
"""
import argparse
import json
import logging
import sys
from datetime import date

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def cmd_create(args) -> None:
    from ml.regulatory.packager import create_package, PackagerError

    period_start = date.fromisoformat(args.period_start)
    period_end   = date.fromisoformat(args.period_end)

    try:
        result = create_package(
            customer_id=args.customer,
            framework=args.framework,
            period_start=period_start,
            period_end=period_end,
            maker_user_id=args.maker,
            company_name=getattr(args, "company", None),
            nace_codes=getattr(args, "nace", None) or [],
            scenarios=getattr(args, "scenarios", None) or ["baseline"],
            time_horizons=getattr(args, "horizons", None) or ["current", "2030", "2050"],
        )
    except PackagerError as e:
        logger.error(f"Package creation failed: {e}")
        sys.exit(1)

    print("\n" + "=" * 60)
    print(f"  DRAFT PACKAGE CREATED")
    print("=" * 60)
    print(f"  package_id  : {result['package_id']}")
    print(f"  framework   : {result['framework']}")
    print(f"  customer    : {result['customer_id']}")
    print(f"  period      : {result['period_start']} → {result['period_end']}")
    print(f"  maker       : {result['maker']}")
    print(f"  n_scores    : {result['n_scores']}")
    print(f"  status      : {result['status']}")
    print()
    print("  Summary:")
    for k, v in result["summary"].items():
        print(f"    {k}: {v}")
    print()
    print("  Next step: run 'approve' with a DIFFERENT user to release.")
    print("  Package ID to share with checker:")
    print(f"    {result['package_id']}")


def cmd_approve(args) -> None:
    from ml.regulatory.packager import (
        approve_package, MakerCheckerViolation,
        PackageAlreadyReleased, PackagerError
    )

    try:
        result = approve_package(
            package_id=args.package_id,
            checker_user_id=args.checker,
        )
    except MakerCheckerViolation as e:
        logger.error(f"4-EYES VIOLATION: {e}")
        sys.exit(1)
    except PackageAlreadyReleased as e:
        logger.error(f"IMMUTABLE: {e}")
        sys.exit(1)
    except PackagerError as e:
        logger.error(f"Approval failed: {e}")
        sys.exit(1)

    print("\n" + "=" * 60)
    print(f"  PACKAGE RELEASED ✓")
    print("=" * 60)
    print(f"  package_id  : {result['package_id']}")
    print(f"  framework   : {result['framework']}")
    print(f"  status      : {result['status']}")
    print(f"  maker       : {result['maker']}")
    print(f"  checker     : {result['checker']}")
    print(f"  released_at : {result['released_at']}")
    print(f"  immutable   : {result['immutable']}")
    print()
    print("  This package is now IMMUTABLE — it cannot be modified.")
    print("  It may be submitted to the regulator.")


def cmd_get(args) -> None:
    from ml.regulatory.packager import get_package

    pkg = get_package(args.package_id)
    if not pkg:
        logger.error(f"Package {args.package_id} not found")
        sys.exit(1)

    print("\n" + "=" * 60)
    print(f"  Package {pkg['package_id']}")
    print("=" * 60)
    for k, v in pkg.items():
        if k == "package_data":
            print(f"  package_data: [use --full to view, --xbrl to export]")
        else:
            print(f"  {k}: {v}")

    if getattr(args, "full", False) and pkg.get("package_data"):
        print("\n--- PACKAGE DATA ---")
        print(json.dumps(pkg["package_data"], indent=2, default=str))

    if getattr(args, "xbrl", None) and pkg.get("package_data"):
        from ml.regulatory.xbrl import write_xbrl
        if not args.lei:
            logger.error("--lei is required when exporting XBRL")
            sys.exit(1)
        path = write_xbrl(
            csrd_package=pkg["package_data"],
            output_path=args.xbrl,
            lei_code=args.lei,
            reporting_currency=getattr(args, "currency", "EUR"),
            company_name=pkg["package_data"].get("company_name"),
        )
        print(f"\n  XBRL exported → {path}")


def cmd_list(args) -> None:
    from ml.regulatory.packager import list_packages

    packages = list_packages(
        customer_id=args.customer,
        framework=getattr(args, "framework", None),
    )

    if not packages:
        print(f"No packages found for customer {args.customer}")
        return

    print(f"\n{'ID'[:36]:<38} {'Framework':<8} {'Status':<10} {'Period':<25} {'Maker'}")
    print("-" * 110)
    for p in packages:
        period = f"{p['period_start']} → {p['period_end']}"
        print(f"{p['package_id']:<38} {p['framework']:<8} {p['status']:<10} {period:<25} {p['maker']}")


def main():
    parser = argparse.ArgumentParser(
        description="Regulatory Package CLI — maker/checker workflow",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # create
    p_create = sub.add_parser("create", help="MAKER: build draft package")
    p_create.add_argument("--customer",     required=True)
    p_create.add_argument("--framework",    required=True, choices=["ECB", "CSRD", "ecb", "csrd"])
    p_create.add_argument("--period-start", required=True, dest="period_start")
    p_create.add_argument("--period-end",   required=True, dest="period_end")
    p_create.add_argument("--maker",        required=True)
    p_create.add_argument("--company",      default=None, help="CSRD: company legal name")
    p_create.add_argument("--nace",         nargs="+", default=[], help="CSRD: NACE sector codes")
    p_create.add_argument("--scenarios",    nargs="+", default=["baseline"])
    p_create.add_argument("--horizons",     nargs="+", default=["current", "2030", "2050"])

    # approve
    p_approve = sub.add_parser("approve", help="CHECKER: release a draft package")
    p_approve.add_argument("--package-id", required=True, dest="package_id")
    p_approve.add_argument("--checker",    required=True)

    # get
    p_get = sub.add_parser("get", help="Retrieve a package by ID")
    p_get.add_argument("--package-id", required=True, dest="package_id")
    p_get.add_argument("--full",       action="store_true", help="Print full package_data JSON")
    p_get.add_argument("--xbrl",       default=None, metavar="PATH",
                       help="Export XBRL instance document to this .xbrl file")
    p_get.add_argument("--lei",        default=None, help="LEI code for XBRL export (20 chars)")
    p_get.add_argument("--currency",   default="EUR", help="Reporting currency (default EUR)")

    # list
    p_list = sub.add_parser("list", help="List packages for a customer")
    p_list.add_argument("--customer",  required=True)
    p_list.add_argument("--framework", default=None, choices=["ECB", "CSRD"])

    args = parser.parse_args()

    dispatch = {
        "create":  cmd_create,
        "approve": cmd_approve,
        "get":     cmd_get,
        "list":    cmd_list,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
