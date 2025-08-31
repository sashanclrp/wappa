# Button Command Media Files

This directory contains media files sent in response to button selections in the `/button` command demo.

## Required Files

Place these files in this directory:

### `kitty.png`
- **Purpose**: Sent when user clicks the "🐱 Kitty" button
- **Format**: PNG or JPG image
- **Size limit**: 5MB maximum
- **Dimensions**: Recommended 500x500px or similar
- **Content**: Image of a cute kitten

### `puppy.png`
- **Purpose**: Sent when user clicks the "🐶 Puppy" button
- **Format**: PNG or JPG image
- **Size limit**: 5MB maximum
- **Dimensions**: Recommended 500x500px or similar
- **Content**: Image of a cute puppy

## How It Works

1. User sends `/button` command
2. App creates interactive button message with "Kitty" and "Puppy" options
3. User clicks one of the buttons
4. App sends the corresponding image file from this directory
5. User receives the image with a caption

## File Sources

You can add your own images:
- Download free images from Unsplash, Pixabay, or similar
- Use your own photos
- Ensure you have rights to use the images
- Keep file sizes reasonable for WhatsApp

## Fallback Behavior

If files are missing:
- App will send a text message instead
- Message will indicate the file is missing
- Button functionality will still work, but without media

## Example Implementation

```python
# In state_handlers.py
if selection_id == "kitty":
    media_file = "kitty.png"
elif selection_id == "puppy":
    media_file = "puppy.png"

media_result = await send_local_media_file(
    messenger=self.messenger,
    recipient=user_id,
    filename=media_file,
    media_subdir="buttons",
    caption=f"Here's your {selection_id}! 🎉"
)
```