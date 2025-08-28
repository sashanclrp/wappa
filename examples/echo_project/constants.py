"""
Echo Project Constants

Shared constants and configuration for comprehensive echo functionality.
Based on the original echo_test_event constants with Wappa framework adaptations.
"""

from datetime import timedelta

# ===== USER STORAGE CONSTANTS =====
USER_DATA_TTL = timedelta(hours=24)
USER_DATA_TTL_HOURS = 24
USER_DATA_TTL_SECONDS = 86400  # 24 hours in seconds

# ===== MESSAGE PROCESSING CONSTANTS =====
ECHO_PROCESSING_DELAY_SECONDS = 3  # Optimized delay for media messages
MEDIA_ECHO_ENABLED = True
METADATA_EXTRACTION_ENABLED = True
USER_STORAGE_ENABLED = True
MESSAGE_CONFIRMATION_ENABLED = True

# ===== MEDIA ECHO CONSTANTS =====
MAX_MEDIA_SIZE_MB = 16  # WhatsApp limit
SUPPORTED_MEDIA_TYPES = ["image", "video", "audio", "document", "sticker"]
MEDIA_ECHO_PREFIX = "🔄 ECHO: "
MEDIA_METADATA_ENABLED = True

# ===== LOCATION ECHO CONSTANTS =====
LOCATION_ECHO_ENABLED = True
LOCATION_METADATA_ENABLED = True

# ===== CONTACT ECHO CONSTANTS =====
CONTACT_ECHO_ENABLED = True
CONTACT_METADATA_ENABLED = True

# ===== STATE CLEANUP CONSTANTS =====
STATE_CLEANUP_ENABLED = True

# ===== BUTTON STATE CONSTANTS =====
BUTTON_ACTIVATION_COMMAND = "/button"
BUTTON_STATE_HANDLER_TYPE = "button"
BUTTON_STATE_TTL = timedelta(minutes=10)
BUTTON_STATE_TTL_SECONDS = 600  # 10 minutes in seconds

# Button IDs
BUTTON_ID_NICE = "nice_button"
BUTTON_ID_YOURS = "button_yours"

# Image paths (relative to echo_project/media/)
IMAGE_PATH_NICE = "media/cf592_POST.png"
IMAGE_PATH_YOURS = "media/WeDancin_RawImg.png"

# Button captions
CAPTION_NICE = "CF592, enjoy"
CAPTION_YOURS = "We Dancin' or Nah?"

# Button messages
BUTTON_SELECTION_PROMPT = "Please select one of the options in the button above to continue."
BUTTON_MESSAGE_BODY = "Choose an option to see a special image!"
BUTTON_MESSAGE_HEADER = "Interactive Demo"
BUTTON_MESSAGE_FOOTER = "Select one option"

# Button titles
BUTTON_TITLE_NICE = "Nice Button"
BUTTON_TITLE_YOURS = "Button yours"

# ===== LIST STATE CONSTANTS =====
LIST_ACTIVATION_COMMAND = "/list"
LIST_STATE_HANDLER_TYPE = "list"
LIST_STATE_TTL = timedelta(minutes=10)
LIST_STATE_TTL_SECONDS = 600  # 10 minutes in seconds

# List row IDs and titles
LIST_ROW_IMAGE = "media_image"
LIST_ROW_VIDEO = "media_video"
LIST_ROW_AUDIO = "media_audio"
LIST_ROW_DOCUMENT = "media_document"

# List row titles and descriptions
LIST_TITLE_IMAGE = "Image"
LIST_TITLE_VIDEO = "Video"
LIST_TITLE_AUDIO = "Audio"
LIST_TITLE_DOCUMENT = "Document"

LIST_DESC_IMAGE = "Get a sample image file"
LIST_DESC_VIDEO = "Get a sample video file"
LIST_DESC_AUDIO = "Get a sample audio file"
LIST_DESC_DOCUMENT = "Get a sample document file"

# Media file paths (relative to echo_project/media/)
MEDIA_PATH_IMAGE = "media/image.png"
MEDIA_PATH_VIDEO = "media/video.mp4"
MEDIA_PATH_AUDIO = "media/audio.ogg"
MEDIA_PATH_DOCUMENT = "media/document.pdf"

# List message content
LIST_MESSAGE_BODY = "Select the media type you'd like to receive!"
LIST_MESSAGE_HEADER = "Media Options"
LIST_MESSAGE_FOOTER = "Choose one option"
LIST_BUTTON_TEXT = "Select Media"
LIST_SECTION_TITLE = "Available Media Types"

# List selection prompt
LIST_SELECTION_PROMPT = "Please select one of the options in the list above to continue."

# ===== CTA CONSTANTS =====
CTA_ACTIVATION_COMMAND = "/cta"
CTA_BUTTON_TEXT = "View Best Practices"
CTA_BUTTON_URL = "https://agency-swarm.ai/core-framework/tools/custom-tools/best-practices"
CTA_MESSAGE_BODY = "Check out the best practices for custom tools in Agency Swarm!"
CTA_MESSAGE_HEADER = "Agency Swarm Documentation"
CTA_MESSAGE_FOOTER = "Click to learn more"

# ===== LOCATION REQUEST CONSTANTS =====
LOCATION_ACTIVATION_COMMAND = "/location"
LOCATION_REQUEST_BODY = "📍 Please share your location to help us provide better service!\n\n💡 Your location is only used for this service and not stored."

# ===== METADATA ECHO CONSTANTS =====
METADATA_ECHO_HEADER = "🔍 *ECHO Test - {message_type} Message Analysis*"
METADATA_ECHO_FOOTER = "🎉 Metadata ECHO analysis complete! This demonstrates the Universal Webhook Interface capabilities."

# ===== MESSAGE CONFIRMATION CONSTANTS =====
TYPING_INDICATOR_ENABLED = True
READ_RECEIPT_ENABLED = True

# ===== ERROR HANDLING CONSTANTS =====
MAX_RETRY_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 1

# ===== LOGGING CONSTANTS =====
LOG_METADATA_EXTRACTION = True
LOG_MEDIA_ECHO_ATTEMPTS = True
LOG_USER_STORAGE = True
LOG_MESSAGE_CONFIRMATION = True

# ===== STATE MANAGEMENT CONSTANTS =====
STATE_KEY_PREFIX = "echo_state"
USER_PROFILE_KEY_PREFIX = "echo_user"

# State types
STATE_TYPE_BUTTON = "button"
STATE_TYPE_LIST = "list"

# ===== COMMAND CONSTANTS =====
SUPPORTED_COMMANDS = [
    BUTTON_ACTIVATION_COMMAND,
    LIST_ACTIVATION_COMMAND,
    CTA_ACTIVATION_COMMAND,
    LOCATION_ACTIVATION_COMMAND
]

# ===== RESPONSE TEMPLATES =====
WELCOME_MESSAGE = """
🎉 Welcome to the Echo Project!

This is a comprehensive demonstration of the Wappa framework capabilities.

✨ **Available Commands:**
• `/button` - Interactive buttons demo
• `/list` - Interactive list with media options
• `/cta` - Call-to-action button demo
• `/location` - Location request demo

🔄 **Echo Features:**
• Send any message to see comprehensive echo
• Media files are echoed back with metadata
• Location and contact sharing supported
• User profiles cached for 24 hours
• Interactive states managed with Redis

Try sending any message or use one of the commands above!
"""

ERROR_MESSAGE_TEMPLATE = "❌ Error: {error}\n\nPlease try again or contact support if the problem persists."

SUCCESS_MESSAGE_TEMPLATE = "✅ {action} completed successfully!"

# ===== MEDIA VALIDATION CONSTANTS =====
ALLOWED_IMAGE_FORMATS = ["png", "jpg", "jpeg", "webp"]
ALLOWED_VIDEO_FORMATS = ["mp4", "3gp", "mov"]
ALLOWED_AUDIO_FORMATS = ["aac", "mp3", "wav", "ogg", "opus"]
ALLOWED_DOCUMENT_FORMATS = ["pdf", "doc", "docx", "txt", "xls", "xlsx", "ppt", "pptx"]

# ===== RATE LIMITING CONSTANTS =====
RATE_LIMIT_WINDOW_SECONDS = 60
RATE_LIMIT_MAX_MESSAGES = 30

# ===== CACHE KEY PATTERNS =====
def get_state_key(user_id: str, state_type: str) -> str:
    """Generate state cache key for user and state type."""
    return f"{STATE_KEY_PREFIX}:{user_id}:{state_type}"

def get_user_profile_key(user_id: str) -> str:
    """Generate user profile cache key."""
    return f"{USER_PROFILE_KEY_PREFIX}:{user_id}"

# ===== FEATURE FLAGS =====
FEATURES = {
    "comprehensive_echo": True,
    "interactive_buttons": True,
    "interactive_lists": True,
    "cta_buttons": True,
    "location_requests": True,
    "user_storage": True,
    "media_echo": True,
    "metadata_extraction": True,
    "message_confirmation": True,
    "state_management": True,
    "error_recovery": True,
    "logging_detailed": True
}

# ===== PERFORMANCE CONSTANTS =====
MAX_CONCURRENT_OPERATIONS = 5
OPERATION_TIMEOUT_SECONDS = 30
CACHE_OPERATION_TIMEOUT = 5

# ===== VALIDATION PATTERNS =====
PHONE_NUMBER_PATTERN = r'^\+?[1-9]\d{1,14}$'
MESSAGE_ID_PATTERN = r'^[a-zA-Z0-9_-]+$'

# ===== DEFAULT RESPONSES =====
DEFAULT_RESPONSES = {
    "processing": "⏳ Processing your request...",
    "completed": "✅ Request completed successfully!",
    "error": "❌ Something went wrong. Please try again.",
    "timeout": "⏱️ Request timed out. Please try again.",
    "invalid_selection": "❌ Invalid selection. Please choose from the available options.",
    "state_expired": "⏰ Your session has expired. Please start over.",
    "feature_disabled": "🚫 This feature is currently disabled.",
    "maintenance": "🔧 System is under maintenance. Please try again later."
}

# ===== WEBHOOK CONSTANTS =====
WEBHOOK_PROCESSING_TIMEOUT = 25  # seconds
WEBHOOK_RETRY_ATTEMPTS = 2
WEBHOOK_RETRY_DELAY = 1  # seconds

# ===== DEBUGGING CONSTANTS =====
DEBUG_ENABLED = False
DEBUG_LOG_WEBHOOK_DATA = False
DEBUG_LOG_STATE_CHANGES = False
DEBUG_LOG_CACHE_OPERATIONS = False