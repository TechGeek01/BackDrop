class Status:
    """Status codes for use with configuration.

    These codes don't reference anything, and only need to differ from
    eachother. Values can be arbitrarily changed without breaking anything
    so long as they remain unique.
    """

    # 0x0 => Selection
    BACKUPSELECT_NO_SELECTION = 0x00
    BACKUPSELECT_MISSING_SOURCE = 0x01
    BACKUPSELECT_MISSING_DEST = 0x02
    BACKUPSELECT_CALCULATING_SOURCE = 0x03
    BACKUPSELECT_INSUFFICIENT_SPACE = 0x04
    BACKUPSELECT_ANALYSIS_WAITING = 0x05

    # 0x1 => Action
    IDLE = 0x10
    BACKUP_ANALYSIS_RUNNING = 0x11
    BACKUP_READY_FOR_ANALYSIS = 0x12
    BACKUP_READY_FOR_BACKUP = 0x13
    BACKUP_BACKUP_RUNNING = 0x14
    BACKUP_HALT_REQUESTED = 0x15
    VERIFICATION_RUNNING = 0x16

    # 0x2 => Save states
    SAVE_PENDING_CHANGES = 0x20
    SAVE_ALL_SAVED = 0x21

    # 0x3 => File operations
    FILE_OPERATION_DELETE = 0x30
    FILE_OPERATION_COPY = 0x31
    FILE_OPERATION_UPDATE = 0x32
    FILE_OPERATION_SUCCESS = 0x3e
    FILE_OPERATION_FAILED = 0x3f

    # 0xe => Update UI
    UPDATEUI_ANALYSIS_BTN = 0xe0
    UPDATEUI_BACKUP_BTN = 0xe1
    UPDATEUI_ANALYSIS_START = 0xe2
    UPDATEUI_ANALYSIS_END = 0xe3
    UPDATEUI_BACKUP_START = 0xe4
    UPDATEUI_BACKUP_END = 0xe5
    UPDATEUI_STATUS_BAR = 0xe6
    UPDATEUI_STATUS_BAR_DETAILS = 0xe7

    # 0xf => Update
    UPDATE_CHECKING = 0xf0
    UPDATE_AVAILABLE = 0xf1
    UPDATE_UP_TO_DATE = 0xf2
    UPDATE_FAILED = 0xf3

    # 0x10 => Lock states and resets
    RESET_ANALYSIS_OUTPUT = 0x100
    UNLOCK_TREE_SELECTION = 0x101
    LOCK_TREE_SELECTION = 0x102
