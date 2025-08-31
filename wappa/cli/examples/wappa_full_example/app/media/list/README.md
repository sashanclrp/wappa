# List Command Media Files

This directory contains media files sent in response to list selections in the `/list` command demo.

## Required Files

Place these files in this directory:

### `image.png`
- **Purpose**: Sent when user selects "🖼️ Image" from the list
- **Format**: PNG or JPG image
- **Size limit**: 5MB maximum
- **Content**: Sample image to demonstrate image sending
- **Suggested**: Colorful demo image, infographic, or screenshot

### `video.mp4`
- **Purpose**: Sent when user selects "🎬 Video" from the list
- **Format**: MP4 video file
- **Size limit**: 16MB maximum
- **Duration**: Keep under 60 seconds for demo purposes
- **Content**: Sample video demonstrating video messaging
- **Suggested**: Short demo video, animation, or screen recording

### `audio.mp3`
- **Purpose**: Sent when user selects "🎵 Audio" from the list
- **Format**: MP3, OGG, or AAC audio file
- **Size limit**: 16MB maximum
- **Duration**: Keep under 2 minutes for demo purposes
- **Content**: Sample audio demonstrating audio messaging
- **Suggested**: Music clip, voice recording, or sound effect

### `document.pdf`
- **Purpose**: Sent when user selects "📄 Document" from the list
- **Format**: PDF document
- **Size limit**: 100MB maximum
- **Content**: Sample document demonstrating document sharing
- **Suggested**: User guide, specification sheet, or informational PDF

## How It Works

1. User sends `/list` command
2. App creates interactive list message with 4 media type options
3. User selects one option from the list
4. App sends the corresponding media file from this directory
5. User receives the media file with a caption

## Interactive List Structure

```json
{
  "title": "📁 Media Files",
  "rows": [
    {"id": "image_file", "title": "🖼️ Image", "description": "Get a sample image file"},
    {"id": "video_file", "title": "🎬 Video", "description": "Get a sample video file"},
    {"id": "audio_file", "title": "🎵 Audio", "description": "Get a sample audio file"},
    {"id": "document_file", "title": "📄 Document", "description": "Get a sample document file"}
  ]
}
```

## File Recommendations

### For Demo/Testing:
- **Image**: Screenshots of the app, logos, or demo graphics
- **Video**: App walkthrough, feature demonstration, or intro video
- **Audio**: Welcome message, jingle, or app sounds
- **Document**: User manual, API documentation, or feature list

### For Production:
- **Image**: Product catalogs, infographics, charts
- **Video**: Product demos, tutorials, testimonials
- **Audio**: Voice messages, audio guides, music
- **Document**: Contracts, invoices, manuals, reports

## WhatsApp Business API Limits

- **Images**: JPEG, PNG up to 5MB, 8-bit RGB or RGBA
- **Videos**: MP4, 3GP up to 16MB, H.264 codec, AAC audio
- **Audio**: AAC, AMR, MP3, M4A, OGG up to 16MB
- **Documents**: TXT, PDF, DOC, DOCX, XLS, XLSX, PPT, PPTX up to 100MB

## Fallback Behavior

If files are missing:
- App will send a text message instead
- Message will indicate the selected media type
- List functionality will still work, but without actual media

## Example Implementation

```python
# In state_handlers.py
media_mapping = {
    "image_file": ("image.png", "image"),
    "video_file": ("video.mp4", "video"),
    "audio_file": ("audio.mp3", "audio"),
    "document_file": ("document.pdf", "document")
}

media_file, media_type = media_mapping.get(selection_id, (None, None))

if media_file:
    await send_local_media_file(
        messenger=self.messenger,
        recipient=user_id,
        filename=media_file,
        media_subdir="list",
        caption=f"Here's your {media_type} file! 🎉"
    )
```