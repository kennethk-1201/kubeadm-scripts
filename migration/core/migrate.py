import sys

from migration.core.migrator import PodMigrator


def main():
    pod_id = sys.argv[1] if len(sys.argv) > 1 else None
    migrator = PodMigrator()
    try:
        migrator.migrate(pod_id)
    except Exception as e:
        print(f"Migration failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
