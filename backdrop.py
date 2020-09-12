import tkinter as tk
from tkinter import ttk, messagebox, font
import win32api
import win32file
import shutil
import os
import wmi
import re
import threading
import pythoncom
import itertools
import subprocess
import clipboard
import time

# Set meta info
appVersion = '1.0.1'

# TODO: When loading a config, warn if drive in config isn't connected
#    If replacement drive is selected that gives sufficient size, prompt for replace confirmation
#    Warn about missing drive once, and allow user to select other drives or redo config after
#        Let this warning be reset if program is re-launched, or a reset button is hit to reset the config
# TODO: Shares are copied to root of drives, so other directories with data are most likely left intact
#     We may need to account for this, by checking for free space, and then adding the size of the existing share directories
#     This would prevent counting for existing data, though it's probably safe to wipe the drive of things that aren't getting copied anyway
#     When we copy, check directory size of source and dest, and if the dest is larger than source, copy those first to free up space for ones that increased
# TODO: Add a button for deleting the config from selected drives
# TODO: Add interactive CLI option if correct parameters are passed in

# Centers a tkinter window
def center(win):
	win.update_idletasks()
	width = win.winfo_width()
	frm_width = win.winfo_rootx() - win.winfo_x()
	win_width = width + 2 * frm_width
	height = win.winfo_height()
	titlebar_height = win.winfo_rooty() - win.winfo_y()
	win_height = height + titlebar_height + frm_width
	x = win.winfo_screenwidth() // 2 - win_width // 2
	y = win.winfo_screenheight() // 2 - win_height // 2
	win.geometry('{}x{}+{}+{}'.format(width, height, x, y))
	win.deiconify()

# Turn an integer representing bytes into a human readable string
def human_filesize(num, suffix='B'):
	for unit in ['', 'Ki', 'Mi', 'Gi', 'Ti', 'Pi', 'Ei', 'Zi']:
		if abs(num) < 1024.0:
			return "%3.2f %s%s" % (num, unit, suffix)
		num /= 1024.0
	return "%.1f%s%s" % (num, 'Yi', suffix)

# Get the proper size of a directory and contents
def get_directory_size(directory):
	total = 0
	try:
		for entry in os.scandir(directory):
			# For each entry, either add filesize to the total, or recurse into the directory
			if entry.is_file():
				total += entry.stat().st_size
			elif entry.is_dir():
				total += get_directory_size(entry.path)
	except NotADirectoryError:
		return os.path.getsize(directory)
	except PermissionError:
		return 0
	except OSError:
		return 0
	return total

# Detect if a thread by a given name is active
def threadNameIsActive(name):
	for thread in threading.enumerate():
		if thread.name == name and thread.is_alive():
			return thread
	return False

class color:
	NORMAL = '#000'
	FADED = '#999'
	BLUE = '#0093c4'
	GREEN = '#6db500'
	GOLD = '#ebb300'
	RED = '#c00'
	GRAY = '#999'

	FINISHED = GREEN
	RUNNING = BLUE
	STOPPED = RED
	PENDING = GRAY

# Set app defaults
sourceDrive = None
backupConfigFile = 'backup.config'
appConfigFile = 'defaults.config'
appDataFolder = os.getenv('LocalAppData') + '\\BackDrop'
elemPadding = 16

config = {
	'shares': [],
	'drives': {}
}

commandList = []

backupThread = None
analysisValid = False

def enumerateCommandInfo():
	global cmdInfoBlocks
	rightArrow = '\U0001f86a'
	downArrow = '\U0001f86e'

	cmdHeaderFont = (None, 9, 'bold')
	cmdStatusFont = (None, 9)

	def toggleCmdInfo(index):
		# Check if arrow needs to be expanded
		expandArrow = cmdInfoBlocks[index]['arrow']['text']
		if expandArrow == rightArrow:
			# Collapsed turns into expanded
			cmdInfoBlocks[index]['arrow'].configure(text = downArrow)
			cmdInfoBlocks[index]['infoFrame'].pack(anchor = 'w')
		else:
			# Expanded turns into collapsed
			cmdInfoBlocks[index]['arrow'].configure(text = rightArrow)
			cmdInfoBlocks[index]['infoFrame'].pack_forget()

		# For some reason, .configure() loses the function bind, so we need to re-set this
		cmdInfoBlocks[index]['arrow'].bind('<Button-1>', lambda event, index = index: toggleCmdInfo(index))

	def copyCmd(index):
		clipboard.copy(cmdInfoBlocks[index]['fullCmd'])

	for widget in backupActivityScrollableFrame.winfo_children():
		widget.destroy()

	cmdInfoBlocks = []
	for i, cmd in enumerate(commandList):
		cmdParts = cmd.split('/mir')
		# cmdSnip = ' '.join(cmdParts[0:3])
		cmdSnip = cmdParts[0].strip()

		config = {}

		config['mainFrame'] = tk.Frame(backupActivityScrollableFrame)
		config['mainFrame'].pack(anchor = 'w', expand = 1)

		# Set up header arrow, trimmed command, and status
		config['headLine'] = tk.Frame(config['mainFrame'])
		config['headLine'].pack(fill = 'x')
		config['arrow'] = tk.Label(config['headLine'], text = rightArrow)
		config['arrow'].pack(side = 'left')
		config['header'] = tk.Label(config['headLine'], text = cmdSnip, font = cmdHeaderFont)
		config['header'].pack(side = 'left')
		config['state'] = tk.Label(config['headLine'], text = 'Pending', font = cmdStatusFont, fg = color.PENDING)
		config['state'].pack(side = 'left')
		config['arrow'].update_idletasks()
		arrowWidth = config['arrow'].winfo_width()

		# Header toggle action click
		config['arrow'].bind('<Button-1>', lambda event, index = i: toggleCmdInfo(index))
		config['header'].bind('<Button-1>', lambda event, index = i: toggleCmdInfo(index))

		# Set up info frame
		config['infoFrame'] = tk.Frame(config['mainFrame'])
		config['cmdLine'] = tk.Frame(config['infoFrame'])
		config['cmdLine'].pack(anchor = 'w')
		tk.Frame(config['cmdLine'], width = arrowWidth).pack(side = 'left')
		config['cmdLineHeader'] = tk.Label(config['cmdLine'], text = 'Full command:', font = cmdHeaderFont)
		config['cmdLineHeader'].pack(side = 'left')
		config['cmdLineTooltip'] = tk.Label(config['cmdLine'], text = '(Click to copy)', font = cmdStatusFont, fg = color.FADED)
		config['cmdLineTooltip'].pack(side = 'left')
		config['fullCmd'] = cmd

		config['lastOutLine'] = tk.Frame(config['infoFrame'])
		config['lastOutLine'].pack(anchor = 'w')
		tk.Frame(config['lastOutLine'], width = arrowWidth).pack(side = 'left')
		config['lastOutHeader'] = tk.Label(config['lastOutLine'], text = 'Out:', font = cmdHeaderFont)
		config['lastOutHeader'].pack(side = 'left')
		config['lastOutResult'] = tk.Label(config['lastOutLine'], text = 'Pending', font = cmdStatusFont, fg = color.PENDING)
		config['lastOutResult'].pack(side = 'left')

		# Handle command trimming
		cmdFont = tk.font.Font(family = None, size = 10, weight = 'normal')
		trimmedCmd = cmd
		maxWidth = backupActivityInfoCanvas.winfo_width() * 0.8
		actualWidth = cmdFont.measure(cmd)

		if actualWidth > maxWidth:
			while actualWidth > maxWidth and len(trimmedCmd) > 1:
				trimmedCmd = trimmedCmd[:-1]
				actualWidth = cmdFont.measure(trimmedCmd + '...')
			trimmedCmd = trimmedCmd + '...'

		config['cmdLineCmd'] = tk.Label(config['cmdLine'], text = trimmedCmd, font = cmdStatusFont)
		config['cmdLineCmd'].pack(side = 'left')

		# Command copy action click
		config['cmdLineHeader'].bind('<Button-1>', lambda event, index = i: copyCmd(index))
		config['cmdLineTooltip'].bind('<Button-1>', lambda event, index = i: copyCmd(index))
		config['cmdLineCmd'].bind('<Button-1>', lambda event, index = i: copyCmd(index))

		# Stats frame
		config['statusStatsLine'] = tk.Frame(config['infoFrame'])
		config['statusStatsLine'].pack(anchor = 'w')
		tk.Frame(config['statusStatsLine'], width = 2 * arrowWidth).pack(side = 'left')
		config['statusStatsFrame'] = tk.Frame(config['statusStatsLine'])
		config['statusStatsFrame'].pack(side = 'left')

		cmdInfoBlocks.append(config)

# TODO: This analysis assumes the drives are going to be empty, aside from the config file
# Other stuff that's not part of the backup will need to be deleted when we actually run it
# TODO: Add a threshold for free space to subtract from drive capacity or free space to account for the config file
def analyzeBackup(shares, drives):
	global backupSummaryTextFrame
	global commandList
	global analysisValid

	if len(threading.enumerate()) <= 2:
		progressBar.configure(mode = 'indeterminate')
		progressBar.start()

	startBackupBtn.configure(state = 'disable')

	# Set UI variables
	summaryHeaderFont = (None, 14)

	for widget in backupSummaryTextFrame.winfo_children():
		widget.destroy()

	tk.Label(backupSummaryTextFrame, text = 'Shares', font = summaryHeaderFont,
		wraplength = backupSummaryFrame.winfo_width() - 2, justify = 'left').pack(anchor = 'w')

	shareInfo = {}
	allShareInfo = {}
	for item in shares:
		shareName = sourceTree.item(item, 'text')
		shareSize = int(sourceTree.item(item, 'values')[1])

		shareInfo[shareName] = shareSize
		allShareInfo[shareName] = shareSize

		tk.Label(backupSummaryTextFrame, text = '%s \u27f6 %s' % (shareName, human_filesize(shareSize)),
			wraplength = backupSummaryFrame.winfo_width() - 2, justify = 'left').pack(anchor = 'w')

	tk.Label(backupSummaryTextFrame, text = 'Drives', font = summaryHeaderFont,
		wraplength = backupSummaryFrame.winfo_width() - 2, justify = 'left').pack(anchor = 'w')

	driveInfo = []
	driveShareList = {}
	for item in drives:
		driveName = destTree.item(item, 'text')
		driveSize = int(destTree.item(item, 'values')[1])

		driveInfo.append({
			'item': item,
			'name': driveName,
			'size': driveSize,
			'free': driveSize
		})

		# Enumerate list for tracking what shares go where
		driveShareList[driveName] = []

		tk.Label(backupSummaryTextFrame, text = '%s \u27f6 %s' % (driveName, human_filesize(driveSize)),
			wraplength = backupSummaryFrame.winfo_width() - 2, justify = 'left').pack(anchor = 'w')

	# For each drive, smallest first, filter list of shares to those that fit
	driveInfo.sort(key = lambda x: x['size'])

	for i, drive in enumerate(driveInfo):
		# Get list of shares small enough to fit on drive
		smallShares = {share: size for share, size in shareInfo.items() if size <= drive['size']}

		# Try every combination of shares that fit to find result that uses most of that drive
		largestSum = 0
		largestSet = []
		for n in range(1, len(smallShares) + 1):
			for subset in itertools.combinations(smallShares.keys(), n):
				combinationTotal = sum(smallShares[share] for share in subset)

				if (combinationTotal > largestSum and combinationTotal <= drive['size']):
					largestSum = combinationTotal
					largestSet = subset

		sharesThatFit = [share for share in largestSet]
		remainingSmallShares = {share: size for (share, size) in smallShares.items() if share not in sharesThatFit}
		shareInfo = {share: size for (share, size) in shareInfo.items() if share not in sharesThatFit}

		# If not all shares fit on smallest drive at once (at least one share has to be put
		# on the next largest drive), check free space on next largest drive
		if len(remainingSmallShares) > 0 and i < (len(driveInfo) - 1):
			notFitTotal = sum(size for size in remainingSmallShares.values())
			nextDrive = driveInfo[i + 1]
			nextDriveFreeSpace = nextDrive['size'] - notFitTotal

			# If free space on next drive is less than total capacity of current drive, it becomes
			# more efficient to skip current drive, and put all shares on the next drive instead
			# NOTE: This applies only if they can all fit on the next drive. If they have to be split
			# across multiple drives after moving them to a larger drive, then it's easier to fit
			# what we can on the small drive, to leave the larger drives available for larger shares
			if notFitTotal <= nextDrive['size']:
				totalSmallShareSpace = sum(size for size in smallShares.values())
				if nextDriveFreeSpace < drive['size'] and totalSmallShareSpace <= nextDrive['size']:
					# Next drive free space less than total on current, so it's optimal to store on next drive instead
					driveShareList[nextDrive['name']].extend([share for share in smallShares.keys()]) # All small shares on next drive
				else:
					# Better to leave on current, but overflow to next drive
					driveShareList[drive['name']].extend(sharesThatFit) # Shares that fit on current drive
					driveShareList[nextDrive['name']].extend([share for share in smallShares.keys() if share not in sharesThatFit]) # Remaining small shares on next drive
			else:
				# If overflow for next drive is more than can fit on that drive, ignore it, put overflow
				# back in pool of shares to sort, and put small drive shares only in current drive
				driveShareList[drive['name']].extend(sharesThatFit) # Shares that fit on current drive

				# Put remaining small shares back into pool to work with for next drive
				shareInfo.update({share: size for share, size in remainingSmallShares.items()})
		else:
			# Fit all small shares onto drive
			driveShareList[drive['name']].extend(sharesThatFit)

		# Calculate space used by shares, and subtract it from capacity to get free space
		usedSpace = sum(allShareInfo[share] for share in driveShareList[drive['name']])
		drive.update({'free': drive['size'] - usedSpace})

	# For each remaining share that needs to be split, sort drives by largest free space, and
	# recurse into the shares to see how it can be split up
	def splitShare(share):
		# Enumerate list for tracking what shares go where
		driveFileList = {drive['name']: [] for drive in driveInfo}

		fileInfo = {}
		for entry in os.scandir(sourceDrive + share):
			if entry.is_file():
				newDirSize = entry.stat().st_size
			elif entry.is_dir():
				newDirSize = get_directory_size(entry.path)

			fileName = entry.path.split('\\')[-1]
			fileInfo[fileName] = newDirSize

		# For splitting shares, sort descending by free space
		driveInfo.sort(reverse = True, key = lambda x: x['free'])

		for i, drive in enumerate(driveInfo):
			# Get list of files small enough to fit on drive
			totalSmallFiles = {file: size for file, size in fileInfo.items() if size <= drive['free']}

			# Since the list of files is truncated to prevent an unreasonably large
			# number of combinations to check, we need to keep processing the file list
			# in chunks to make sure we check if all files can be fit on one drive
			# TODO: This loop logic may need to be copied to the main share portion, though this is only necessary if the user selects a large number of shares
			filesThatFit = []
			processedSmallFiles = []
			processedFileSize = 0
			while len(processedSmallFiles) < len(totalSmallFiles):
				# Trim the list of small files to those that aren't already processed
				smallFiles = {file: size for (file, size) in totalSmallFiles.items() if file not in processedSmallFiles}

				# Make sure we don't end with an unreasonable number of combinations to go through
				# by sorting by largest first, and truncating
				# Sorting files first, since files can't be split, so it's preferred to have directories last
				listFiles = {}
				listDirs = {}
				for file, size in smallFiles.items():
					if os.path.isfile(sourceDrive + '\\' + share + '\\' + file):
						listFiles[file] = size
					elif os.path.isdir(sourceDrive + '\\' + share + '\\' + file):
						listDirs[file] = size

				# Sort file list by largest first, and truncate to prevent unreasonably large number of combinations
				smallFiles = sorted(listFiles.items(), key = lambda x: x[1], reverse = True)
				smallFiles.extend(sorted(listDirs.items(), key = lambda x: x[1], reverse = True))
				trimmedSmallFiles = {file[0]: file[1] for file in smallFiles[:15]}
				smallFiles = {file[0]: file[1] for file in smallFiles}

				# Try every combination of shares that fit to find result that uses most of that drive
				largestSum = 0
				largestSet = []
				for n in range(1, len(trimmedSmallFiles) + 1):
					for subset in itertools.combinations(trimmedSmallFiles.keys(), n):
						combinationTotal = sum(trimmedSmallFiles[file] for file in subset)

						if (combinationTotal > largestSum and combinationTotal <= drive['free'] - processedFileSize):
							largestSum = combinationTotal
							largestSet = subset

				filesThatFit.extend([file for file in largestSet])
				processedSmallFiles.extend([file for file in trimmedSmallFiles.keys()])
				fileInfo = {file: size for (file, size) in fileInfo.items() if file not in largestSet}

				# Subtract file size of each batch of files from the free space on the drive so the next batch sorts properly
				processedFileSize += sum([size for (file, size) in smallFiles.items() if file in largestSet])

			# Assign files to drive, and subtract filesize from free space
			# NOTE: Since we're sorting by largest free space first, there's no cases to
			# move to a larger drive. This means all files that can fit should be put on the
			# drive they fit on
			driveFileList[drive['name']].extend(filesThatFit)
			driveInfo[i]['free'] -= processedFileSize

		shareSplitSummary = [{
			'share': share,
			'files': driveFileList,
			'exclusions': [file for file in fileInfo.keys()]
		}]

		for file in fileInfo.keys():
			filePath = share + '\\' + file
			shareSplitSummary.extend(splitShare(filePath))

		return shareSplitSummary

	# driveShareList contains info about whole shares mapped to drives
	# Use this to build the list of non-exclusion robocopy commands
	commandList = []
	for drive, shares in driveShareList.items():
		if len(shares) > 0:
			commandList.extend(['robocopy "%s" "%s" /mir' % (sourceDrive + share, drive + share) for share in shares])

	# For each share that needs splitting, split each one
	# For each resulting folder in the summary, get list of files
	# For each drive, exclusions are files on other drives, plus explicit exclusions

	# For shares larger than all drives, recurse into each share
	for share in shareInfo.keys():
		summary = splitShare(share)

		# Each summary contains a split share, and any split subfolders, starting with
		# the share and recursing into the directories
		for directory in summary:
			shareName = directory['share']
			shareFiles = directory['files']
			shareExclusions = directory['exclusions']

			allFiles = shareFiles.copy()
			allFiles['exclusions'] = shareExclusions

			sourcePathStub = sourceDrive + shareName + '\\'

			# For each drive, gather list of files to be written to other drives, and
			# use that as exclusions
			for drive, files in shareFiles.items():
				if len(files) > 0:
					rawExclusions = allFiles.copy()
					rawExclusions.pop(drive, None)

					masterExclusions = [files for files in rawExclusions.values()]

					fileExclusions = [sourcePathStub + file for file in masterExclusions if os.path.isfile(sourcePathStub + file)]
					dirExclusions = [sourcePathStub + file for file in masterExclusions if os.path.isdir(sourcePathStub + file)]
					xs = (' /xf "' + '" "'.join(fileExclusions) + '"') if len(fileExclusions) > 0 else ''
					xd = (' /xd "' + '" "'.join(dirExclusions) + '"') if len(dirExclusions) > 0 else ''

					commandList.append('robocopy "%s" "%s" /mir%s%s' % (sourceDrive + shareName, drive + shareName, xd, xs))
				driveShareList[drive].append(shareName)

	enumerateCommandInfo()

	tk.Label(backupSummaryTextFrame, text = 'Summary', font = summaryHeaderFont,
		wraplength = backupSummaryFrame.winfo_width() - 2, justify = 'left').pack(anchor = 'w')
	for drive, shares in driveShareList.items():
		tk.Label(backupSummaryTextFrame, text = '%s \u27f6 %s' % (drive, ', '.join(shares)),
			wraplength = backupSummaryFrame.winfo_width() - 2, justify = 'left').pack(anchor = 'w')

	analysisValid = True

	startBackupBtn.configure(state = 'normal')

	if len(threading.enumerate()) <= 2:
		progressBar.configure(mode = 'determinate')
		progressBar.stop()

def sanityCheck():
	sourceSelection = sourceTree.selection()
	destSelection = destTree.selection()
	selectionOk = len(sourceSelection) > 0 and len(destSelection) > 0

	shareTotal = 0
	driveTotal = 0

	if selectionOk:
		for item in sourceSelection:
			# Add total space of selection
			shareSize = sourceTree.item(item, 'values')[1]
			shareTotal = shareTotal + int(shareSize)

		for item in destSelection:
			# Add total space of selection
			driveSize = destTree.item(item, 'values')[1]
			driveTotal = driveTotal + int(driveSize)

		if shareTotal < driveTotal:
			return True

	return False

def startBackupAnalysis():
	if sanityCheck():
		backupAnalysisThread = threading.Thread(target = analyzeBackup, args = [sourceTree.selection(), destTree.selection()], name = 'Backup Analysis', daemon = True)
		backupAnalysisThread.start()

root = tk.Tk()
root.attributes('-alpha', 0.0)
root.title('BackDrop - Unraid Drive Backup Tool')
# root.iconbitmap('.\\App\\Shim\\assets\\unpack_128.ico')
root.resizable(False, False)
root.geometry('1200x700')
# root.minsize(1200, 700)

center(root)
root.attributes('-alpha', 1.0)

mainFrame = tk.Frame(root)
mainFrame.pack(fill = 'both', expand = 1, padx = elemPadding, pady = (elemPadding / 2, elemPadding))

# Set some default styling
buttonWinStyle = ttk.Style()
buttonWinStyle.theme_use('vista')
buttonWinStyle.configure('win.TButton', padding = 5)

buttonWinStyle = ttk.Style()
buttonWinStyle.theme_use('vista')
buttonWinStyle.configure('danger.TButton', padding = 5, background = '#b00')

buttonIconStyle = ttk.Style()
buttonIconStyle.theme_use('vista')
buttonIconStyle.configure('icon.TButton', width = 2, height = 1, padding = 1, font = (None, 15), background = '#00bfe6')

# TODO: Make changes to existing config check the existing for missing drives, and delete the config file from drives we unselected if there's multiple drives in a config
def writeSettingToFile(setting, file):
	dirParts = file.split('\\')
	pathDir = '\\'.join(dirParts[:-1])

	if not os.path.exists(pathDir):
		os.mkdir(pathDir)

	f = open(file, 'w')
	f.write(setting)
	f.close()

def readSettingFromFile(file, default, verifyData = None):
	if os.path.exists(file) and os.path.isfile(file):
		f = open(file, 'r')
		rawConfig = f.read().split('\n')
		f.close()

		setting = rawConfig[0]

		if verifyData is not None and setting not in verifyData:
			setting = default
			writeSettingToFile(default, file)

		return setting
	else:
		return default

# Set source drives and start to set up source dropdown
sourceDriveDefault = tk.StringVar()
driveList = win32api.GetLogicalDriveStrings().split('\000')[:-1]
remoteDrives = [drive for drive in driveList if win32file.GetDriveType(drive) == 4]
sourceDrive = readSettingFromFile(appDataFolder + '\\sourceDrive.default', remoteDrives[0], remoteDrives)
sourceDriveDefault.set(sourceDrive)

if not os.path.exists(appDataFolder + '\\sourceDrive.default') or not os.path.isfile(appDataFolder + '\\sourceDrive.default'):
	writeSettingToFile(sourceDrive, appDataFolder + '\\sourceDrive.default')

# Tree frames for tree and scrollbar
sourceTreeFrame = tk.Frame(mainFrame)
sourceTreeFrame.grid(row = 1, column = 0, sticky = 'ns')
destTreeFrame = tk.Frame(mainFrame)
destTreeFrame.grid(row = 1, column = 1, sticky = 'ns', padx = (elemPadding, 0))

# Progress/status values
progressBar = ttk.Progressbar(mainFrame, maximum = 100)
progressBar.grid(row = 10, column = 0, columnspan = 3, sticky = 'ew', pady = (elemPadding, 0))

sourceTree = ttk.Treeview(sourceTreeFrame, columns = ('size', 'rawsize'))
sourceTree.heading('#0', text = 'Share')
sourceTree.column('#0', width = 200)
sourceTree.heading('size', text = 'Size')
sourceTree.column('size', width = 80)
sourceTree['displaycolumns'] = ('size')

sourceTree.pack(side = 'left')
sourceShareScroll = ttk.Scrollbar(sourceTreeFrame, orient = 'vertical', command = sourceTree.yview)
sourceShareScroll.pack(side = 'left', fill = 'y')
sourceTree.configure(xscrollcommand = sourceShareScroll.set)

# There's an invisible 1px background on buttons. When changing this in icon buttons, it becomes
# visible, so 1px needs to be added back
sourceMetaFrame = tk.Frame(mainFrame)
sourceMetaFrame.grid(row = 2, column = 0, sticky = 'nsew', pady = (1, elemPadding))
tk.Grid.columnconfigure(sourceMetaFrame, 0, weight = 1)

shareSpaceFrame = tk.Frame(sourceMetaFrame)
shareSpaceFrame.grid(row = 0, column = 0)
shareSelectedSpace = tk.Label(shareSpaceFrame, text = 'Selected: ' + human_filesize(0))
shareSelectedSpace.grid(row = 0, column = 0)
shareTotalSpace = tk.Label(shareSpaceFrame, text = 'Total: ~' + human_filesize(0))
shareTotalSpace.grid(row = 0, column = 1, padx = (12, 0))

def loadSource():
	global analysisValid
	if len(threading.enumerate()) <= 2:
		progressBar.configure(mode = 'indeterminate')
		progressBar.start()

	analysisValid = False

	# Empty tree in case this is being refreshed
	sourceTree.delete(*sourceTree.get_children())

	shareSelectedSpace.configure(text = 'Selected: ' + human_filesize(0))
	shareTotalSpace.configure(text = 'Total: ~' + human_filesize(0))

	# Enumerate list of shares in source
	for directory in next(os.walk(sourceDrive))[1]:
		sourceTree.insert(parent = '', index = 'end', text = directory, values = ('Unknown', 0))

	if len(threading.enumerate()) <= 2:
		progressBar.configure(mode = 'determinate')
		progressBar.stop()

loadSource()

def startRefreshSource():
	if not threadNameIsActive('Load Source'):
		sourceLoadThread = threading.Thread(target = loadSource, name = 'Load Source', daemon = True)
		sourceLoadThread.start()

refreshSourceBtn = ttk.Button(sourceMetaFrame, text = '\u2b6e', command = startRefreshSource, style = 'icon.TButton')
refreshSourceBtn.grid(row = 0, column = 1)

def changeSourceDrive(selection):
	global sourceDrive
	sourceDrive = selection
	startRefreshSource()
	writeSettingToFile(sourceDrive, appDataFolder + '\\sourceDrive.default')

sourceSelectFrame = tk.Frame(mainFrame)
sourceSelectFrame.grid(row = 0, column = 0, pady = (0, elemPadding / 2))
tk.Label(sourceSelectFrame, text = 'Source:').pack(side = 'left')
sourceSelectMenu = ttk.OptionMenu(sourceSelectFrame, sourceDriveDefault, sourceDrive, *tuple(remoteDrives), command = changeSourceDrive)
sourceSelectMenu.pack(side = 'left', padx = (12, 0))

# TODO: Calculate total space of all shares
prevShareSelection = []
def shareSelectCalc():
	global prevShareSelection
	global analysisValid
	if len(threading.enumerate()) <= 2:
		progressBar.configure(mode = 'indeterminate')
		progressBar.start()

	# Update config and space totals
	def updateInfo():
		selectedTotal = 0
		selectedShareList = []
		for item in sourceTree.selection():
			# Write selected shares to config
			selectedShareList.append(sourceTree.item(item, 'text'))

			# Add total space of selection
			if sourceTree.item(item, 'values')[0] != 'Unknown':
				# Add total space of selection
				shareSize = sourceTree.item(item, 'values')[1]
				selectedTotal = selectedTotal + int(shareSize)

		shareSelectedSpace.configure(text = 'Selected: ' + human_filesize(selectedTotal))
		config['shares'] = selectedShareList

		shareTotal = 0
		totalIsApprox = False
		totalPrefix = 'Total: '
		for item in sourceTree.get_children():
			shareTotal += int(sourceTree.item(item, 'values')[1])

			# If total is not yet approximate, check if the item hasn't been calculated
			if not totalIsApprox and sourceTree.item(item, 'values')[0] == 'Unknown':
				totalIsApprox = True
				totalPrefix += '~'

		shareTotalSpace.configure(text = totalPrefix + human_filesize(shareTotal))

	selected = sourceTree.selection()

	# If selection is different than last time, invalidate the analysis
	selectMatch = [share for share in selected if share in prevShareSelection]
	if len(selected) != len(prevShareSelection) or len(selectMatch) != len(prevShareSelection):
		analysisValid = False
		startBackupBtn.configure(state = 'disable')

	prevShareSelection = [share for share in selected]

	# Check if items in selection need to be calculated
	for item in selected:
		# If new selected item hasn't been calculated, calculate it on the fly
		if sourceTree.item(item, 'values')[0] == 'Unknown':
			startAnalysisBtn.configure(state = 'disable')

			shareName = sourceTree.item(item, 'text')
			# print('...')
			newShareSize = get_directory_size(sourceDrive + shareName)
			sourceTree.set(item, 'size', human_filesize(newShareSize))
			sourceTree.set(item, 'rawsize', newShareSize)
			# print('%s => %s' % (shareName, human_filesize(newShareSize)))

		updateInfo()

	sharesAllKnown = True
	for item in sourceTree.selection():
		if sourceTree.item(item, 'values')[0] == 'Unknown':
			sharesAllKnown = False
	if sharesAllKnown:
		startAnalysisBtn.configure(state = 'normal')

	if len(threading.enumerate()) <= 2:
		progressBar.configure(mode = 'determinate')
		progressBar.stop()

# TODO: See if we can find a way to prevent the same share from being calculated twice in different threads
def loadSourceInBackground(event):
	sourceItemLoadThread = threading.Thread(target = shareSelectCalc, name = 'Load Source Selection', daemon = True)
	sourceItemLoadThread.start()

sourceTree.bind("<<TreeviewSelect>>", loadSourceInBackground)

destTree = ttk.Treeview(destTreeFrame, columns = ('size', 'rawsize', 'configfile', 'vid', 'serial'))
destTree.heading('#0', text = 'Drive')
destTree.column('#0', width = 50)
destTree.heading('size', text = 'Size')
destTree.column('size', width = 80)
destTree.heading('configfile', text = 'Config file')
destTree.column('configfile', width = 100)
destTree.heading('vid', text = 'Volume ID')
destTree.column('vid', width = 100)
destTree.heading('serial', text = 'Serial')
destTree.column('serial', width = 200)
destTree['displaycolumns'] = ('size', 'configfile', 'vid', 'serial')

destTree.pack(side = 'left')
driveSelectScroll = ttk.Scrollbar(destTreeFrame, orient = 'vertical', command = destTree.yview)
driveSelectScroll.pack(side = 'left', fill = 'y')
destTree.configure(xscrollcommand = driveSelectScroll.set)

def loadDest():
	global destDriveMap
	if len(threading.enumerate()) <= 2:
		progressBar.configure(mode = 'indeterminate')
		progressBar.start()

	driveList = win32api.GetLogicalDriveStrings()
	driveList = driveList.split('\000')[:-1]

	# Associate logical drives with physical drives, and map them to physical serial numbers
	logicalPhysicalMap = {}
	pythoncom.CoInitialize()
	try:
		for physicalDisk in wmi.WMI().Win32_DiskDrive():
			for partition in physicalDisk.associators("Win32_DiskDriveToDiskPartition"):
				logicalPhysicalMap.update({logicalDisk.DeviceID[0]: physicalDisk.SerialNumber.strip() for logicalDisk in partition.associators("Win32_LogicalDiskToPartition")})
	finally:
		pythoncom.CoUninitialize()

	# Empty tree in case this is being refreshed
	destTree.delete(*destTree.get_children())

	# Enumerate drive list to find info about all non-source drives
	totalUsage = 0
	destDriveMap = {}
	destDriveLetterToInfo = {}
	for drive in driveList:
		if drive != sourceDrive:
			driveType = win32file.GetDriveType(drive)
			if driveType not in (4, 6): # Make sure drive isn't REMOTE or RAMDISK
				driveSize = shutil.disk_usage(drive).total
				vsn = os.stat(drive).st_dev
				vsn = '{:04X}-{:04X}'.format(vsn >> 16, vsn & 0xffff)
				try:
					serial = logicalPhysicalMap[drive[0]]
				except KeyError:
					serial = 'Not Found'

				# Add drive to drive list
				destDriveMap[vsn] = drive[0]
				destDriveLetterToInfo[drive[0]] = {
					'vid': vsn,
					'serial': serial
				}

				driveHasConfigFile = os.path.exists('%s%s' % (drive, backupConfigFile)) and os.path.isfile('%s%s' % (drive, backupConfigFile))

				totalUsage = totalUsage + driveSize
				destTree.insert(parent = '', index = 'end', text = drive, values = (human_filesize(driveSize), driveSize, 'Yes' if driveHasConfigFile else '', vsn, serial))

	driveTotalSpace.configure(text = 'Available: ' + human_filesize(totalUsage))

	if len(threading.enumerate()) <= 2:
		progressBar.configure(mode = 'determinate')
		progressBar.stop()

def startRefreshDest():
	if not threadNameIsActive('Refresh destination'):
		refreshDestThread = threading.Thread(target = loadDest, name = 'Refresh destination', daemon = True)
		refreshDestThread.start()

# There's an invisible 1px background on buttons. When changing this in icon buttons, it becomes
# visible, so 1px needs to be added back
destMetaFrame = tk.Frame(mainFrame)
destMetaFrame.grid(row = 2, column = 1, sticky = 'nsew', pady = (1, elemPadding))
tk.Grid.columnconfigure(destMetaFrame, 0, weight = 1)

driveSpaceFrame = tk.Frame(destMetaFrame)
driveSpaceFrame.grid(row = 0, column = 0)
driveSelectedSpace = tk.Label(driveSpaceFrame, text = 'Selected: ' + human_filesize(0))
driveSelectedSpace.grid(row = 0, column = 0)
driveTotalSpace = tk.Label(driveSpaceFrame, text = 'Available: ' + human_filesize(0))
driveTotalSpace.grid(row = 0, column = 1, padx = (12, 0))

refreshDestBtn = ttk.Button(destMetaFrame, text = '\u2b6e', command = startRefreshDest, style = 'icon.TButton')
refreshDestBtn.grid(row = 0, column = 1)
startAnalysisBtn = ttk.Button(destMetaFrame, text = 'Analyze Backup', command = startBackupAnalysis, style = 'win.TButton')
startAnalysisBtn.grid(row = 0, column = 2)

# Using the current config, make selections in the GUI to match
def selectFromConfig():
	global driveSelectBind

	# Get list of shares in config
	sourceTreeIdList = [item for item in sourceTree.get_children() if sourceTree.item(item, 'text') in config['shares']]

	sourceTree.focus(sourceTreeIdList[-1])
	sourceTree.selection_set(tuple(sourceTreeIdList))

	# Get list of drives where volume ID is in config
	driveTreeIdList = [item for item in destTree.get_children() if destTree.item(item, 'values')[3] in config['vidList']]

	# Only redo the selection if the config data is different from the current
	# selection (that is, the drive we selected to load a config is not the only
	# drive listed in the config)
	# Because of the <<TreeviewSelect>> handler, re-selecting the same single item
	# would get stuck into an endless loop of trying to load the config
	# TODO: Is there a better way to handle this config loading selection handler conflict?
	if destTree.selection() != tuple(driveTreeIdList):
		destTree.unbind('<<TreeviewSelect>>', driveSelectBind)

		destTree.focus(driveTreeIdList[-1])
		destTree.selection_set(tuple(driveTreeIdList))

		driveSelectBind = destTree.bind("<<TreeviewSelect>>", handleDriveSelectionClick)

def readConfigFile(file):
	global config
	if os.path.exists(file) and os.path.isfile(file):
		f = open(file, 'r')
		rawConfig = f.read().split('\n\n')
		f.close()

		newConfig = {}

		# Each chunk after splitting on \n\n is a header followed by config stuff
		for chunk in rawConfig:
			splitChunk = chunk.split('\n')
			header = re.search('\[(.*)\]', splitChunk.pop(0)).group(1)

			if header == 'shares':
				# Shares is a single line, comma separated list of shares
				newConfig['shares'] = splitChunk[0].split(',')
			elif header == 'drives':
				# Drives is a list, where each line is one drive, and each drive lists
				# comma separated volume ID and physical serial
				newConfig['drives'] = []
				newConfig['vidList'] = []
				for drive in splitChunk:
					drive = drive.split(',')
					newConfig['vidList'].append(drive[0])
					newConfig['drives'].append({
						'vid': drive[0],
						'serial': drive[1]
					})

		config = newConfig
		selectFromConfig()

# Parse drive selection, and calculate values needed
prevSelection = 0
prevDriveSelection = []
def handleDriveSelectionClick():
	global prevSelection
	global prevDriveSelection
	global analysisValid

	if len(threading.enumerate()) <= 2:
		progressBar.configure(mode = 'indeterminate')
		progressBar.start()

	selected = destTree.selection()

	# If selection is different than last time, invalidate the analysis
	selectMatch = [drive for drive in selected if drive in prevDriveSelection]
	if len(selected) != len(prevDriveSelection) or len(selectMatch) != len(prevDriveSelection):
		analysisValid = False
		startBackupBtn.configure(state = 'disable')

	prevDriveSelection = [share for share in selected]

	# Check if newly selected drive has a config file
	# NOTE: We only want to do this if the click is the first selection (that is,
	# there are no other drives selected except the one we clicked)
	if prevSelection <= len(selected) and len(selected) == 1:
		prevSelection = len(selected)
		selectedDriveLetter = destTree.item(selected[0], 'text')[0]
		configFilePath = '%s:/%s' % (selectedDriveLetter, backupConfigFile)
		if os.path.exists(configFilePath) and os.path.isfile(configFilePath):
			# Found config file, so read it
			readConfigFile(configFilePath)
	else:
		prevSelection = len(selected)

	selectedTotal = 0
	selectedDriveList = []
	for item in selected:
		# Write drive IDs to config
		driveVals = destTree.item(item, 'values')
		selectedDriveList.append({
			'vid': driveVals[3],
			'serial': driveVals[4]
		})

		driveSize = driveVals[1]
		selectedTotal = selectedTotal + int(driveSize)

	driveSelectedSpace.configure(text = 'Selected: ' + human_filesize(selectedTotal))
	config['drives'] = selectedDriveList

	if len(threading.enumerate()) <= 2:
		progressBar.configure(mode = 'determinate')
		progressBar.stop()

def selectDriveInBackground(event):
	driveSelectThread = threading.Thread(target = handleDriveSelectionClick, name = 'Drive Select', daemon = True)
	driveSelectThread.start()

driveSelectBind = destTree.bind("<<TreeviewSelect>>", selectDriveInBackground)

# TODO: Make changes to existing config check the existing for missing drives, and delete the config file from drives we unselected if there's multiple drives in a config
def writeConfigFile():
	if len(config['shares']) > 0 and len(config['drives']) > 0:
		driveConfigList = ''.join(['\n%s,%s' % (drive['vid'], drive['serial']) for drive in config['drives']])

		# For each drive letter, get drive info, and write file
		for drive in config['drives']:
			f = open('%s:/%s' % (destDriveMap[drive['vid']], backupConfigFile), 'w')
			# f.write('[id]\n%s,%s\n\n' % (driveInfo['vid'], driveInfo['serial']))
			f.write('[shares]\n%s\n\n' % (','.join(config['shares'])))

			f.write('[drives]')
			f.write(driveConfigList)

			f.close()
	else:
		pass
		# print('You must select at least one share, and at least one drive')

# Add activity frame for backup status output
tk.Grid.rowconfigure(mainFrame, 5, weight = 1)
backupActivityFrame = tk.Frame(mainFrame)
backupActivityFrame.grid(row = 5, column = 0, columnspan = 2, sticky = 'nsew')

backupActivityInfoCanvas = tk.Canvas(backupActivityFrame)
backupActivityInfoCanvas.pack(side = 'left', fill = 'both', expand = 1)
backupActivityScroll = ttk.Scrollbar(backupActivityFrame, orient = 'vertical', command = backupActivityInfoCanvas.yview)
backupActivityScroll.pack(side = 'left', fill = 'y')
backupActivityScrollableFrame = ttk.Frame(backupActivityInfoCanvas)
backupActivityScrollableFrame.bind(
	'<Configure>', lambda e: backupActivityInfoCanvas.configure(
		scrollregion = backupActivityInfoCanvas.bbox('all')
	)
)

backupActivityInfoCanvas.create_window((0, 0), window = backupActivityScrollableFrame, anchor = 'nw')
backupActivityInfoCanvas.configure(yscrollcommand = backupActivityScroll.set)

# commandList = ['robocopy "R:\\atmg" "E:\\atmg" /mir', 'robocopy "R:\\documents" "E:\\documents" /mir', 'robocopy "R:\\backups" "F:\\backups" /mir /xd "Macrium Reflect"', 'robocopy "R:\\backups\\Macrium Reflect" "F:\\backups\\Macrium Reflect" /mir /xd "Main Desktop Boot Drive" "Office Desktop Boot Drive" /xf "Main Desktop Win10 Pre-Reinstall-00-00.mrimg" "AsusLaptop-Original-Win10-00-00.mrimg" "Office Desktop Pre10 - 12-24-2019-00-00.mrimg" "AndyLaptop-Win10-PreUbuntu-00-00.mrimg" "Asus Laptop Win10 Pre-Manjaro 2-26-2020-00-00.mrimg" "B0AA9BDCCD59E188-00-00.mrimg" "AndyLaptop-Ubuntu1810-00-00.mrimg" "WinME-HP-Pavillion-00-00.mrimg" "AndyLaptop-ManjaroArchitectKDE-00-00.mrimg" "Dad Full Clone 1-5-2014.7z" "AsusLaptop-Kali-8-10-2020-00-00.mrimg" "Win98-Gateway-00-00.mrimg" "AsusLaptop_Android-x86_9.0_8-11-2020-00-00.mrimg" "Win10 Reflect Rescue 7.2.4808.iso" "Win7 Reflect Rescue 7.2.4228.iso" "macrium_reflect_v7_user_guide.pdf" "Untitled.json"', 'robocopy "R:\\backups\\Macrium Reflect" "G:\\backups\\Macrium Reflect" /mir /xd "Asus Laptop Boot Drive" "Main Desktop User Files" "School Drive"']
# commandList = ['robocopy "R:\\documents" "H:\\documents" /mir']
# enumerateCommandInfo()

tk.Grid.columnconfigure(mainFrame, 2, weight = 1)

rightSideFrame = tk.Frame(mainFrame)
rightSideFrame.grid(row = 0, column = 2, rowspan = 6, sticky = 'nsew', pady = (elemPadding / 2, 0))

backupSummaryFrame = tk.Frame(rightSideFrame)
backupSummaryFrame.pack(fill = 'both', expand = 1, padx = (elemPadding, 0))
backupSummaryFrame.update()

backupTitle = tk.Label(backupSummaryFrame, text = 'Analysis Summary', font = (None, 20))
backupTitle.pack()

brandingFrame = tk.Frame(rightSideFrame)
brandingFrame.pack()

tk.Label(brandingFrame, text = 'BackDrop', font = (None, 28), fg = color.GREEN).pack(side = 'left')
tk.Label(brandingFrame, text = 'v' + appVersion, font = (None, 10), fg = color.FADED).pack(side = 'left', anchor = 's', pady = (0, 6))

backupHalted = False

def runBackup():
	global backupHalted
	global process

	if not analysisValid:
		return

	if len(threading.enumerate()) <= 2:
		progressBar.configure(mode = 'indeterminate')
		progressBar.start()

	# Reset halt flag if it's been tripped
	backupHalted = False

	# Write config file to drives
	writeConfigFile()

	for i, cmd in enumerate(commandList):
		cmdInfoBlocks[i]['state'].configure(text = 'Pending', fg = color.PENDING)
		cmdInfoBlocks[i]['lastOutResult'].configure(text = 'Pending', fg = color.PENDING)

	startBackupBtn.configure(text = 'Halt Backup', command = killBackup, style = 'danger.TButton')

	for i, cmd in enumerate(commandList):
		process = subprocess.Popen(cmd, shell = True, stdout = subprocess.PIPE, stdin = subprocess.DEVNULL, stderr = subprocess.DEVNULL)
		# process = subprocess.Popen(cmd, shell=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

		while not backupHalted and process.poll() is None:
			try:
				out = process.stdout.readline().decode().strip()
				cmdInfoBlocks[i]['state'].configure(text = 'Running', fg = color.RUNNING)
				cmdInfoBlocks[i]['lastOutResult'].configure(text = out.strip(), fg = color.NORMAL)
			except Exception as e:
				pass
		process.terminate()

		if not backupHalted:
			cmdInfoBlocks[i]['state'].configure(text = 'Done', fg = color.FINISHED)
			cmdInfoBlocks[i]['lastOutResult'].configure(text = 'Done', fg = color.FINISHED)
		else:
			cmdInfoBlocks[i]['state'].configure(text = 'Aborted', fg = color.STOPPED)
			cmdInfoBlocks[i]['lastOutResult'].configure(text = 'Aborted', fg = color.STOPPED)
			break

	if len(threading.enumerate()) <= 2:
		progressBar.configure(mode = 'determinate')
		progressBar.stop()

	startBackupBtn.configure(text = 'Run Backup', command = startBackup, style = 'win.TButton')

def startBackup():
	global backupThread
	if sanityCheck():
		backupThread = threading.Thread(target = runBackup, name = 'Backup', daemon = True)
		backupThread.start()

def killBackup():
	global backupHalted
	backupHalted = True

	try:
		process.terminate()
	except:
		pass

# Add placeholder to backup analysis
backupSummaryTextFrame = tk.Frame(backupSummaryFrame)
backupSummaryTextFrame.pack(fill = 'x')
tk.Label(backupSummaryTextFrame, text = 'This area will summarize the backup that\'s been configured.',
	wraplength = backupSummaryFrame.winfo_width() - 2, justify = 'left').pack(anchor = 'w')
tk.Label(backupSummaryTextFrame, text = 'Please start a backup analysis to generate a summary.',
	wraplength = backupSummaryFrame.winfo_width() - 2, justify = 'left').pack(anchor = 'w')
startBackupBtn = ttk.Button(backupSummaryFrame, text = 'Run Backup', command = startBackup, state = 'disable', style = 'win.TButton')
startBackupBtn.pack(pady = elemPadding / 2)

loadThread = threading.Thread(target = loadDest, name = 'Init', daemon = True)
loadThread.start()

def onClose():
	if backupThread and backupThread.is_alive():
		if messagebox.askokcancel('Quit?', 'There\'s still a background process running. Are you sure you want to kill it?'):
			backupHalted = True
			time.sleep(2)
			root.destroy()
	else:
		root.destroy()

root.protocol('WM_DELETE_WINDOW', onClose)
root.mainloop()