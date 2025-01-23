import sys
from migration.core.restorer import PodRestorer

def main():
    if len(sys.argv) != 2:
        print("Usage: python -m migration.core.restore <checkpoint_dir>")
        sys.exit(1)

    checkpoint_dir = sys.argv[1]
    restorer = PodRestorer()
    try:
        success = restorer.restore_pod(checkpoint_dir)
        if not success:
            print("Pod restoration failed")
            sys.exit(1)
    except Exception as e:
        print(f"Error during pod restoration: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
