import requests
import re

from bin.status import Status

class UpdateHandler:
    def __init__(self, currentVersion, updateCallback, statusChangeFn=None):
        """
        Args:
            currentVersion (String): The current version of the program.
            updateCallback (def): The function to call with update results.
            statusChangeFn (def): The function to call when changing status.
        """

        self.currentVersion = currentVersion

        if statusChangeFn is not None:
            self.statusChangeFn = statusChangeFn
        else:
            self.statusChangeFn = None

        self.updateCallback = updateCallback

    def __getLatestVersion(self):
        """Get the latest version of the program.

        Returns:
            dict: Update information.
            dict.latest (String): The latest version.
            dict.download (String[]): A list of URLs for all assets.
        """

        response = requests.get('https://api.github.com/repos/TechGeek01/BackDrop/releases/latest')
        jsonResponse = response.json()

        return {
            'latest': jsonResponse['tag_name'],
            'download': [asset['browser_download_url'] for asset in jsonResponse['assets']]
        }

    def __parseVersion(self, versionString):
        """Parse a version string into it's appropriate parts.

        Args:
            versionString (String): The string of the version to check.

        Returns:
            dict: The version components parsed.
                dict.major (int): Major version.
                dict.minor (int): Minor version.
                dict.patch (int): Patch version.
                dict.dev (dict): Development version.
                dict.dev.stage (String): Development stage.
                dict.dev.count (int): Development version.
        """

        m = re.search(r'(\d+)\.(\d+)\.(\d+)(?:-([A_Za-z]+)\.(\d+))?', versionString)

        if m.group(4) is not None and m.group(5) is not None:
            # Dev version exists
            devVersion = {
                'stage': m.group(4).lower(),
                'version': int(m.group(5))
            }
        else:
            devVersion = None

        return {
            'major': int(m.group(1)),
            'minor': int(m.group(2)),
            'patch': int(m.group(3)),
            'dev': devVersion
        }

    def __currentIsLatestVersion(self, currentVersion, latestVersion):
        """Check if the current version is the latest version or newer.

        Args:
            currentVersion (parseVersion): The current version to compare.
            latestVersion (parseVersion): The latest version to compare to.

        Returns:
            bool: True if current version is latest version, false otherwise.
        """

        # Compare major version
        if currentVersion['major'] < latestVersion['major']:
            # Major version is older
            return False
        elif currentVersion['major'] > latestVersion['major']:
            # Major version is newer
            return True

        # Major versions match
        # Compare minor version
        if currentVersion['minor'] < latestVersion['minor']:
            # Minor version is older
            return False
        elif currentVersion['minor'] > latestVersion['minor']:
            # Minor version is newer
            return True

        # Minor versions match
        # Compare patch version
        if currentVersion['patch'] < latestVersion['patch']:
            # Patch version is older
            return False
        elif currentVersion['patch'] > latestVersion['patch']:
            # Patch version is newer
            return True

        devStageRank = {
            'pre': 0,
            'alpha': 1,
            'beta': 2,
            'rc': 3
        }

        # Versions match
        # Compare development tags
        if currentVersion['dev'] is None and latestVersion['dev'] is None:
            # Neither version has dev tag, so versions are identical
            return True
        elif currentVersion['dev'] is not None and latestVersion['dev'] is None:
            # Latest is not dev
            return False
        elif currentVersion['dev'] is None and latestVersion['dev'] is not None:
            # Latest is dev
            return True
        else:
            currentDevStageRank = devStageRank[currentVersion['dev']['stage']] if currentVersion['dev']['stage'] in devStageRank.keys() else -1
            latestDevStageRank = devStageRank[latestVersion['dev']['stage']] if latestVersion['dev']['stage'] in devStageRank.keys() else -1

            if currentDevStageRank > latestDevStageRank:
                # Current dev stage is ranked higher
                return True
            elif currentDevStageRank < latestDevStageRank:
                # Latest dev stage is ranked higher
                return False
            elif currentVersion['dev']['version'] >= latestVersion['dev']['version']:
                # Current dev version is same or newer than latest
                return True
            else:
                # Latest is newer dev version
                return False

    def check(self):
        """Check for updates.

        Returns:
            dict: The update info
            dict.currentVersion (String): The curent version string.
            dict.updateAvailable (bool): Whether or not an update is available.
            dict.latestVersion (String): The latest version.
            dict.download (String[]): A list of downloads for each latest asset.
        """

        self.statusChangeFn(Status.UPDATE_CHECKING)

        latestVersion = self.__getLatestVersion()
        updateInfo = {
            'currentVersion': self.currentVersion,
            'updateAvailable': not self.__currentIsLatestVersion(self.__parseVersion(self.currentVersion), self.__parseVersion(latestVersion['latest'])),
            'latestVersion': latestVersion['latest'],
            'download': latestVersion['download']
        }

        self.statusChangeFn(Status.UPDATE_AVAILABLE if updateInfo['updateAvailable'] else Status.UPDATE_UP_TO_DATE)
        self.updateCallback(updateInfo)

        return updateInfo
