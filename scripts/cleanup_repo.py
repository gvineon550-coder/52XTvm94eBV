import os
import subprocess

JUNK_FILES = [
    "report.txt",
    "romaxa55_report.txt",
    "iptvorg_report.txt",
    "ufotv_report.txt",
    "quality_report.txt",
    "romaxa55_unstable.m3u",
    "iptvorg_unstable.m3u",
    "ufotv_unstable.m3u",
    "quality_results.csv",
    "duplicates_report.txt",
    "bad_urls_report.txt",
]


def git_rm(path):
    try:
        subprocess.run(["git", "rm", "-f", "--ignore-unmatch", path],
                       check=True, capture_output=True, text=True)
        return True
    except Exception as e:
        print("  error: " + str(e))
        return False


def main():
    removed = 0
    for path in JUNK_FILES:
        if os.path.exists(path):
            if git_rm(path):
                print("  removed: " + path)
                removed += 1
        else:
            # Файла нет на диске — но мог остаться в git-индексе
            subprocess.run(["git", "rm", "-f", "--ignore-unmatch", "--cached", path],
                           capture_output=True, text=True)

    print("")
    print("Removed from disk: " + str(removed))
    print("Done")


main()
