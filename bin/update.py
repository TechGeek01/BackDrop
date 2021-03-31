import requests
import re

from bin.status import Status

class UpdateHandler:
    def __init__(self, current_version, update_callback, status_change_fn=None):
        """
        Args:
            current_version (String): The current version of the program.
            update_callback (def): The function to call with update results.
            status_change_fn (def): The function to call when changing status.
        """

        self.current_version = current_version

        if status_change_fn is not None:
            self.status_change_fn = status_change_fn
        else:
            self.status_change_fn = None

        self.update_callback = update_callback

    def __get_latest_version(self):
        """Get the latest version of the program.

        Returns:
            dict: Update information.
            dict.latest (String): The latest version.
            dict.download (String[]): A list of URLs for all assets.
        """

        response = requests.get('https://api.github.com/repos/TechGeek01/BackDrop/releases/latest')
        json_response = response.json()

        return {
            'latest': json_response['tag_name'],
            'download': [asset['browser_download_url'] for asset in json_response['assets']]
        }

    def __parse_version(self, version_string):
        """Parse a version string into it's appropriate parts.

        Args:
            version_string (String): The string of the version to check.

        Returns:
            dict: The version components parsed.
                dict.major (int): Major version.
                dict.minor (int): Minor version.
                dict.patch (int): Patch version.
                dict.dev (dict): Development version.
                dict.dev.stage (String): Development stage.
                dict.dev.count (int): Development version.
        """

        m = re.search(r'(\d+)\.(\d+)\.(\d+)(?:-([A_Za-z]+)\.(\d+))?', version_string)

        if m.group(4) is not None and m.group(5) is not None:
            # Dev version exists
            dev_version = {
                'stage': m.group(4).lower(),
                'version': int(m.group(5))
            }
        else:
            dev_version = None

        return {
            'major': int(m.group(1)),
            'minor': int(m.group(2)),
            'patch': int(m.group(3)),
            'dev': dev_version
        }

    def __current_is_latest_version(self, current_version, latest_version):
        """Check if the current version is the latest version or newer.

        Args:
            current_version (parse_version): The current version to compare.
            latest_version (parse_version): The latest version to compare to.

        Returns:
            bool: True if current version is latest version, false otherwise.
        """

        # Compare major version
        if current_version['major'] < latest_version['major']:
            # Major version is older
            return False
        elif current_version['major'] > latest_version['major']:
            # Major version is newer
            return True

        # Major versions match
        # Compare minor version
        if current_version['minor'] < latest_version['minor']:
            # Minor version is older
            return False
        elif current_version['minor'] > latest_version['minor']:
            # Minor version is newer
            return True

        # Minor versions match
        # Compare patch version
        if current_version['patch'] < latest_version['patch']:
            # Patch version is older
            return False
        elif current_version['patch'] > latest_version['patch']:
            # Patch version is newer
            return True

        dev_stage_rank = {
            'pre': 0,
            'alpha': 1,
            'beta': 2,
            'rc': 3
        }

        # Versions match
        # Compare development tags
        if current_version['dev'] is None and latest_version['dev'] is None:
            # Neither version has dev tag, so versions are identical
            return True
        elif current_version['dev'] is not None and latest_version['dev'] is None:
            # Latest is not dev
            return False
        elif current_version['dev'] is None and latest_version['dev'] is not None:
            # Latest is dev
            return True
        else:
            current_dev_stage_rank = dev_stage_rank[current_version['dev']['stage']] if current_version['dev']['stage'] in dev_stage_rank.keys() else -1
            latest_dev_stage_rank = dev_stage_rank[latest_version['dev']['stage']] if latest_version['dev']['stage'] in dev_stage_rank.keys() else -1

            if current_dev_stage_rank > latest_dev_stage_rank:
                # Current dev stage is ranked higher
                return True
            elif current_dev_stage_rank < latest_dev_stage_rank:
                # Latest dev stage is ranked higher
                return False
            elif current_version['dev']['version'] >= latest_version['dev']['version']:
                # Current dev version is same or newer than latest
                return True
            else:
                # Latest is newer dev version
                return False

    def check(self):
        """Check for updates.

        Returns:
            dict: The update info
            dict.current_version (String): The curent version string.
            dict.updateAvailable (bool): Whether or not an update is available.
            dict.latestVersion (String): The latest version.
            dict.download (String[]): A list of downloads for each latest asset.
        """

        self.status_change_fn(Status.UPDATE_CHECKING)

        try:
            latest_version = self.__get_latest_version()
            update_info = {
                'current_version': self.current_version,
                'updateAvailable': not self.__current_is_latest_version(self.__parse_version(self.current_version), self.__parse_version(latest_version['latest'])),
                'latestVersion': latest_version['latest'],
                'download': latest_version['download']
            }

            self.status_change_fn(Status.UPDATE_AVAILABLE if update_info['updateAvailable'] else Status.UPDATE_UP_TO_DATE)
            self.update_callback(update_info)
        except Exception:
            update_info = {}
            self.status_change_fn(Status.UPDATE_FAILED)

        return update_info
