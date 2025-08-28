# Sample Media Files for Echo Project

This directory contains sample media files used for testing the Echo Project's interactive features.

## Required Files

The following files are referenced in the project constants and should be placed in this directory:

### Interactive Button Images
- `cf592_POST.png` - Image for "Nice Button" selection
- `WeDancin_RawImg.png` - Image for "Button yours" selection

### Interactive List Media Samples
- `image.png` - Sample image file for list selection demo
- `video.mp4` - Sample video file for list selection demo
- `audio.ogg` - Sample audio file for list selection demo
- `document.pdf` - Sample document file for list selection demo

## Usage

These files are used by the `MediaProcessor` class to demonstrate:

1. **Button Interactions**: When users select interactive buttons, specific images are sent as responses
2. **List Interactions**: When users select media types from lists, corresponding sample files are sent
3. **Media Echo Testing**: Files can be sent to test the echo functionality with different media types

## File Requirements

- **Images**: PNG, JPEG, WebP formats (max 5MB)
- **Videos**: MP4, 3GP formats (max 16MB)
- **Audio**: OGG, MP3, AAC formats (max 16MB)
- **Documents**: PDF, DOC, TXT formats (max 100MB)

## Creating Sample Files

Since this is a development/testing environment, you can create simple placeholder files:

```bash
# Create sample image (1x1 pixel PNG)
echo 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg==' | base64 -d > image.png

# Create sample document
echo 'Sample PDF content for testing' > document.txt && mv document.txt document.pdf

# For audio and video files, you'll need actual media files or can use online generators
```

## Integration with Wappa Framework

The `MediaProcessor` class handles:
- Loading these files from the media directory
- Sending them via WhatsApp Business API
- Fallback handling when files are missing
- Media metadata extraction and echo functionality

## Security Note

In production environments:
- Use proper media file validation
- Implement file size limits
- Scan files for malware
- Use CDN for media distribution
- Implement access controls