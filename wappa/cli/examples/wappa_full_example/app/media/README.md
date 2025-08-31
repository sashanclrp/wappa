# Media Files Directory

This directory contains media files used by the Wappa Full Example application for interactive demonstrations.

## Directory Structure

```
media/
├── buttons/          # Media files for button command responses
│   ├── kitty.png     # Image sent when user selects "Kitty" button
│   └── puppy.png     # Image sent when user selects "Puppy" button
└── list/             # Media files for list command responses
    ├── image.png     # Sample image file for list selection
    ├── video.mp4     # Sample video file for list selection
    ├── audio.mp3     # Sample audio file for list selection
    └── document.pdf  # Sample document file for list selection
```

## Usage

The application automatically serves these files when users interact with:

1. **Button Command** (`/button`):
   - User selects "🐱 Kitty" → sends `buttons/kitty.png`
   - User selects "🐶 Puppy" → sends `buttons/puppy.png`

2. **List Command** (`/list`):
   - User selects "🖼️ Image" → sends `list/image.png`
   - User selects "🎬 Video" → sends `list/video.mp4`
   - User selects "🎵 Audio" → sends `list/audio.mp3`
   - User selects "📄 Document" → sends `list/document.pdf`

## File Requirements

- **Images**: PNG, JPG formats (max 5MB)
- **Videos**: MP4 format (max 16MB)
- **Audio**: MP3, OGG formats (max 16MB)
- **Documents**: PDF format (max 100MB)

## Adding Your Own Files

Replace the placeholder files with your own media:

1. Add your files to the appropriate subdirectories
2. Use the exact filenames as listed above
3. Ensure files meet WhatsApp Business API size limits
4. Test with the interactive commands to verify functionality

## Notes

- Files are loaded from the local filesystem
- The media handler automatically detects file types
- If files are missing, fallback text messages are sent instead
- This is a demonstration setup - in production, you might use cloud storage or CDN