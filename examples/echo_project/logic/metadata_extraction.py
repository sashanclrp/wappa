"""
Metadata Extraction Logic

Extracts comprehensive metadata from webhook messages and builds
rich metadata responses for echo functionality.
"""

from datetime import datetime
from typing import Any, Dict, Optional

from ..constants import METADATA_ECHO_HEADER, METADATA_ECHO_FOOTER


async def extract_message_metadata(webhook, message_type: str) -> Dict[str, Any]:
    """
    Extract comprehensive metadata from webhook message.
    
    Args:
        webhook: IncomingMessageWebhook
        message_type: Type of message (text, image, video, etc.)
        
    Returns:
        Dictionary with extracted metadata
    """
    try:
        metadata = {
            "message_type": message_type,
            "extraction_timestamp": datetime.utcnow().isoformat() + 'Z',
            "webhook_metadata": {},
            "user_metadata": {},
            "message_metadata": {},
            "platform_metadata": {}
        }
        
        # Extract webhook-level metadata
        if hasattr(webhook, 'get_webhook_timestamp'):
            metadata["webhook_metadata"]["timestamp"] = webhook.get_webhook_timestamp()
        if hasattr(webhook, 'message') and webhook.message:
            metadata["webhook_metadata"]["message_id"] = webhook.message.message_id
            
        # Extract user metadata
        if hasattr(webhook, 'user') and webhook.user:
            user = webhook.user
            metadata["user_metadata"].update({
                "user_id": user.user_id,
                "profile_name": user.profile_name if hasattr(user, 'profile_name') else None,
                "display_name": user.display_name if hasattr(user, 'display_name') else None
            })
            
        # Extract tenant/platform metadata
        if hasattr(webhook, 'tenant') and webhook.tenant:
            tenant = webhook.tenant
            metadata["platform_metadata"].update({
                "tenant_key": tenant.get_tenant_key() if hasattr(tenant, 'get_tenant_key') else None,
                "phone_number_id": tenant.phone_number_id if hasattr(tenant, 'phone_number_id') else None,
                "business_account_id": tenant.business_account_id if hasattr(tenant, 'business_account_id') else None
            })
            
        # Extract message-specific metadata
        message = webhook.message
        if message:
            metadata["message_metadata"].update({
                "message_id": message.message_id,
                "timestamp": message.timestamp if hasattr(message, 'timestamp') else None,
                "message_type": message_type
            })
            
            # Add type-specific metadata
            if message_type == "text":
                metadata["message_metadata"]["text_content"] = webhook.get_message_text()
                metadata["message_metadata"]["text_length"] = len(webhook.get_message_text() or "")
                
            elif message_type in ["image", "video", "audio", "document"]:
                # Media-specific metadata
                if hasattr(message, 'media_id'):
                    metadata["message_metadata"]["media_id"] = message.media_id
                if hasattr(message, 'filename'):
                    metadata["message_metadata"]["filename"] = message.filename
                if hasattr(message, 'mime_type'):
                    metadata["message_metadata"]["mime_type"] = message.mime_type
                if hasattr(message, 'file_size'):
                    metadata["message_metadata"]["file_size"] = message.file_size
                if hasattr(message, 'sha256'):
                    metadata["message_metadata"]["sha256"] = message.sha256
                if hasattr(message, 'caption'):
                    metadata["message_metadata"]["caption"] = message.caption
                    
            elif message_type == "location":
                # Location-specific metadata
                if hasattr(message, 'latitude'):
                    metadata["message_metadata"]["latitude"] = message.latitude
                if hasattr(message, 'longitude'):
                    metadata["message_metadata"]["longitude"] = message.longitude
                if hasattr(message, 'name'):
                    metadata["message_metadata"]["location_name"] = message.name
                if hasattr(message, 'address'):
                    metadata["message_metadata"]["location_address"] = message.address
                if hasattr(message, 'url'):
                    metadata["message_metadata"]["location_url"] = message.url
                    
            elif message_type == "contacts":
                # Contact-specific metadata
                if hasattr(message, 'contacts'):
                    metadata["message_metadata"]["contact_count"] = len(message.contacts)
                    contact_names = []
                    for contact in message.contacts[:3]:  # First 3 contacts
                        if hasattr(contact, 'name') and contact.name:
                            contact_names.append(contact.name.formatted_name)
                    metadata["message_metadata"]["contact_names"] = contact_names
                    
        # Add extraction summary
        metadata["extraction_summary"] = {
            "total_fields": sum(len(v) for v in metadata.values() if isinstance(v, dict)),
            "has_user_data": bool(metadata["user_metadata"]),
            "has_message_data": bool(metadata["message_metadata"]),
            "has_platform_data": bool(metadata["platform_metadata"]),
            "extraction_successful": True
        }
        
        return metadata
        
    except Exception as e:
        return {
            "message_type": message_type,
            "extraction_timestamp": datetime.utcnow().isoformat() + 'Z',
            "extraction_error": str(e),
            "extraction_successful": False
        }


async def build_metadata_response(message_type: str, metadata: Dict[str, Any], 
                                  content_preview: Optional[str] = None) -> str:
    """
    Build rich metadata response for echo.
    
    Args:
        message_type: Type of message
        metadata: Extracted metadata
        content_preview: Optional content preview
        
    Returns:
        Formatted metadata response string
    """
    try:
        # Header
        header = METADATA_ECHO_HEADER.format(message_type=message_type.upper())
        
        # Build sections
        sections = [header, ""]
        
        # Message info section
        sections.append("📋 **Message Information:**")
        if metadata.get("message_metadata"):
            msg_meta = metadata["message_metadata"]
            sections.append(f"• Type: {message_type.upper()}")
            sections.append(f"• Message ID: {msg_meta.get('message_id', 'N/A')}")
            if msg_meta.get("timestamp"):
                sections.append(f"• Timestamp: {msg_meta['timestamp']}")
                
            # Type-specific details
            if message_type == "text" and msg_meta.get("text_length"):
                sections.append(f"• Text Length: {msg_meta['text_length']} characters")
                if content_preview and len(content_preview) > 50:
                    sections.append(f"• Preview: {content_preview[:50]}...")
                elif content_preview:
                    sections.append(f"• Content: {content_preview}")
                    
            elif message_type in ["image", "video", "audio", "document"]:
                if msg_meta.get("filename"):
                    sections.append(f"• Filename: {msg_meta['filename']}")
                if msg_meta.get("mime_type"):
                    sections.append(f"• MIME Type: {msg_meta['mime_type']}")
                if msg_meta.get("file_size"):
                    size_mb = round(msg_meta['file_size'] / (1024 * 1024), 2)
                    sections.append(f"• File Size: {size_mb} MB")
                if msg_meta.get("media_id"):
                    sections.append(f"• Media ID: {msg_meta['media_id'][:20]}...")
                    
            elif message_type == "location":
                if msg_meta.get("latitude") and msg_meta.get("longitude"):
                    sections.append(f"• Coordinates: {msg_meta['latitude']}, {msg_meta['longitude']}")
                if msg_meta.get("location_name"):
                    sections.append(f"• Name: {msg_meta['location_name']}")
                if msg_meta.get("location_address"):
                    sections.append(f"• Address: {msg_meta['location_address']}")
                    
            elif message_type == "contacts":
                if msg_meta.get("contact_count"):
                    sections.append(f"• Contact Count: {msg_meta['contact_count']}")
                if msg_meta.get("contact_names"):
                    names = ", ".join(msg_meta['contact_names'][:2])
                    sections.append(f"• Names: {names}{'...' if msg_meta['contact_count'] > 2 else ''}")
        
        sections.append("")
        
        # User info section
        sections.append("👤 **User Information:**")
        if metadata.get("user_metadata"):
            user_meta = metadata["user_metadata"]
            sections.append(f"• User ID: {user_meta.get('user_id', 'N/A')}")
            if user_meta.get("profile_name"):
                sections.append(f"• Profile Name: {user_meta['profile_name']}")
            if user_meta.get("display_name"):
                sections.append(f"• Display Name: {user_meta['display_name']}")
        
        sections.append("")
        
        # Platform info section
        sections.append("🏢 **Platform Information:**")
        if metadata.get("platform_metadata"):
            platform_meta = metadata["platform_metadata"]
            if platform_meta.get("phone_number_id"):
                sections.append(f"• Phone Number ID: {platform_meta['phone_number_id']}")
            if platform_meta.get("business_account_id"):
                sections.append(f"• Business Account ID: {platform_meta['business_account_id']}")
            if platform_meta.get("tenant_key"):
                sections.append(f"• Tenant Key: {platform_meta['tenant_key']}")
        
        sections.append("")
        
        # Extraction summary
        if metadata.get("extraction_summary"):
            summary = metadata["extraction_summary"]
            sections.append("📊 **Extraction Summary:**")
            sections.append(f"• Total Fields: {summary.get('total_fields', 0)}")
            sections.append(f"• Extraction Time: {metadata.get('extraction_timestamp', 'N/A')}")
            sections.append(f"• Success: {'✅ Yes' if summary.get('extraction_successful') else '❌ No'}")
        
        sections.append("")
        sections.append(METADATA_ECHO_FOOTER)
        
        return "\n".join(sections)
        
    except Exception as e:
        return f"❌ Error building metadata response: {str(e)}"