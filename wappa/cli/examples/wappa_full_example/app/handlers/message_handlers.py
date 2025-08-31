"""
Message handlers for different message types in the Wappa Full Example application.

This module provides handlers for processing and echoing different types of messages
including text, media, location, contact, and interactive messages.
"""

import time

from wappa.webhooks import IncomingMessageWebhook

from ..models.user_models import UserProfile
from ..utils.cache_utils import CacheHelper
from ..utils.media_handler import MediaHandler, relay_webhook_media
from ..utils.metadata_extractor import MetadataExtractor


class MessageHandlers:
    """Collection of message handlers for different message types."""

    def __init__(self, messenger, cache_factory, logger):
        """
        Initialize message handlers.

        Args:
            messenger: IMessenger instance for sending messages
            cache_factory: Cache factory for data persistence
            logger: Logger instance
        """
        self.messenger = messenger
        self.cache_helper = CacheHelper(cache_factory)
        self.media_handler = MediaHandler()
        self.logger = logger

    async def handle_text_message(
        self, webhook: IncomingMessageWebhook, user_profile: UserProfile
    ) -> dict[str, any]:
        """
        Handle text message with echo functionality.

        Args:
            webhook: IncomingMessageWebhook with text message
            user_profile: User profile for tracking

        Returns:
            Result dictionary with operation status
        """
        try:
            start_time = time.time()

            # Extract message content
            text_content = webhook.get_message_text()
            user_id = webhook.user.user_id
            message_id = webhook.message.message_id

            self.logger.info(
                f"📝 Processing text message from {user_id}: '{text_content[:50]}'"
            )

            # Extract and format metadata
            metadata = MetadataExtractor.extract_metadata(webhook, start_time)
            metadata_text = MetadataExtractor.format_metadata_for_user(metadata)

            # Send metadata response
            metadata_result = await self.messenger.send_text(
                recipient=user_id, text=metadata_text, reply_to_message_id=message_id
            )

            if not metadata_result.success:
                self.logger.error(f"Failed to send metadata: {metadata_result.error}")
                return {"success": False, "error": "Failed to send metadata"}

            # Send echo response
            echo_text = f"Echo - {text_content}"
            echo_result = await self.messenger.send_text(
                recipient=user_id, text=echo_text
            )

            if not echo_result.success:
                self.logger.error(f"Failed to send echo: {echo_result.error}")
                return {"success": False, "error": "Failed to send echo"}

            # Update user activity
            await self.cache_helper.update_user_activity(user_id, "text")

            # Store message in history
            await self.cache_helper.store_message_history(
                user_id,
                {
                    "message_id": message_id,
                    "type": "text",
                    "content": text_content,
                    "timestamp": webhook.timestamp.isoformat(),
                    "echo_sent": True,
                },
            )

            processing_time = int((time.time() - start_time) * 1000)
            self.logger.info(f"✅ Text message processed in {processing_time}ms")

            return {
                "success": True,
                "message_type": "text",
                "metadata_sent": True,
                "echo_sent": True,
                "processing_time_ms": processing_time,
            }

        except Exception as e:
            self.logger.error(f"❌ Error handling text message: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    async def handle_media_message(
        self, webhook: IncomingMessageWebhook, user_profile: UserProfile
    ) -> dict[str, any]:
        """
        Handle media message with relay functionality.

        Args:
            webhook: IncomingMessageWebhook with media message
            user_profile: User profile for tracking

        Returns:
            Result dictionary with operation status
        """
        try:
            start_time = time.time()

            user_id = webhook.user.user_id
            message_id = webhook.message.message_id
            message_type = webhook.get_message_type_name()

            self.logger.info(f"🎬 Processing {message_type} message from {user_id}")

            # Extract media information
            media_info = await self.media_handler.get_media_info_from_webhook(webhook)
            if not media_info:
                return {"success": False, "error": "No media found in webhook"}

            # Extract and format metadata
            metadata = MetadataExtractor.extract_metadata(webhook, start_time)
            metadata_text = MetadataExtractor.format_metadata_for_user(metadata)

            # Send metadata response
            metadata_result = await self.messenger.send_text(
                recipient=user_id, text=metadata_text, reply_to_message_id=message_id
            )

            if not metadata_result.success:
                self.logger.error(f"Failed to send metadata: {metadata_result.error}")
                return {"success": False, "error": "Failed to send metadata"}

            # Relay the same media using media_id
            relay_result = await relay_webhook_media(
                messenger=self.messenger, webhook=webhook, recipient=user_id
            )

            if not relay_result["success"]:
                self.logger.error(f"Failed to relay media: {relay_result.get('error')}")

                # Send fallback text response if media relay fails
                fallback_text = f"📎 Media echo - {message_type} (relay failed, media_id: {media_info.get('media_id', 'unknown')[:20]}...)"
                await self.messenger.send_text(recipient=user_id, text=fallback_text)

            # Update user activity
            await self.cache_helper.update_user_activity(user_id, "media")

            # Store message in history
            await self.cache_helper.store_message_history(
                user_id,
                {
                    "message_id": message_id,
                    "type": message_type,
                    "media_id": media_info.get("media_id"),
                    "media_type": media_info.get("type"),
                    "timestamp": webhook.timestamp.isoformat(),
                    "relay_success": relay_result["success"],
                },
            )

            processing_time = int((time.time() - start_time) * 1000)
            self.logger.info(
                f"✅ {message_type} message processed in {processing_time}ms"
            )

            return {
                "success": True,
                "message_type": message_type,
                "metadata_sent": True,
                "media_relayed": relay_result["success"],
                "media_info": media_info,
                "processing_time_ms": processing_time,
            }

        except Exception as e:
            self.logger.error(f"❌ Error handling media message: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    async def handle_location_message(
        self, webhook: IncomingMessageWebhook, user_profile: UserProfile
    ) -> dict[str, any]:
        """
        Handle location message with echo functionality.

        Args:
            webhook: IncomingMessageWebhook with location message
            user_profile: User profile for tracking

        Returns:
            Result dictionary with operation status
        """
        try:
            start_time = time.time()

            user_id = webhook.user.user_id
            message_id = webhook.message.message_id

            self.logger.info(f"📍 Processing location message from {user_id}")

            # Extract location data
            latitude = getattr(webhook.message, "latitude", None)
            longitude = getattr(webhook.message, "longitude", None)
            location_name = getattr(webhook.message, "name", None)
            location_address = getattr(webhook.message, "address", None)

            if latitude is None or longitude is None:
                return {"success": False, "error": "Invalid location data"}

            # Extract and format metadata
            metadata = MetadataExtractor.extract_metadata(webhook, start_time)
            metadata_text = MetadataExtractor.format_metadata_for_user(metadata)

            # Send metadata response
            metadata_result = await self.messenger.send_text(
                recipient=user_id, text=metadata_text, reply_to_message_id=message_id
            )

            if not metadata_result.success:
                self.logger.error(f"Failed to send metadata: {metadata_result.error}")
                return {"success": False, "error": "Failed to send metadata"}

            # Echo the same location
            location_result = await self.messenger.send_location(
                latitude=float(latitude),
                longitude=float(longitude),
                recipient=user_id,
                name=location_name,
                address=location_address,
            )

            if not location_result.success:
                self.logger.error(f"Failed to send location: {location_result.error}")

                # Send fallback text response
                fallback_text = f"📍 Location echo - {latitude}, {longitude}"
                if location_name:
                    fallback_text += f" ({location_name})"
                await self.messenger.send_text(recipient=user_id, text=fallback_text)

            # Update user activity
            await self.cache_helper.update_user_activity(user_id, "location")

            # Store message in history
            await self.cache_helper.store_message_history(
                user_id,
                {
                    "message_id": message_id,
                    "type": "location",
                    "latitude": latitude,
                    "longitude": longitude,
                    "name": location_name,
                    "address": location_address,
                    "timestamp": webhook.timestamp.isoformat(),
                    "echo_sent": location_result.success,
                },
            )

            processing_time = int((time.time() - start_time) * 1000)
            self.logger.info(f"✅ Location message processed in {processing_time}ms")

            return {
                "success": True,
                "message_type": "location",
                "metadata_sent": True,
                "location_echoed": location_result.success,
                "coordinates": {"latitude": latitude, "longitude": longitude},
                "processing_time_ms": processing_time,
            }

        except Exception as e:
            self.logger.error(f"❌ Error handling location message: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    async def handle_contact_message(
        self, webhook: IncomingMessageWebhook, user_profile: UserProfile
    ) -> dict[str, any]:
        """
        Handle contact message with echo functionality.

        Args:
            webhook: IncomingMessageWebhook with contact message
            user_profile: User profile for tracking

        Returns:
            Result dictionary with operation status
        """
        try:
            start_time = time.time()

            user_id = webhook.user.user_id
            message_id = webhook.message.message_id

            self.logger.info(f"👥 Processing contact message from {user_id}")

            # Extract contact data
            contacts = getattr(webhook.message, "contacts", [])
            if not isinstance(contacts, list):
                contacts = [contacts] if contacts else []

            if not contacts:
                return {"success": False, "error": "No contact data found"}

            # Extract and format metadata
            metadata = MetadataExtractor.extract_metadata(webhook, start_time)
            metadata_text = MetadataExtractor.format_metadata_for_user(metadata)

            # Send metadata response
            metadata_result = await self.messenger.send_text(
                recipient=user_id, text=metadata_text, reply_to_message_id=message_id
            )

            if not metadata_result.success:
                self.logger.error(f"Failed to send metadata: {metadata_result.error}")
                return {"success": False, "error": "Failed to send metadata"}

            # Echo the contacts (send the first contact)
            contact_to_send = contacts[0] if contacts else None
            contact_sent = False

            if contact_to_send:
                # Convert contact to the format expected by messenger
                contact_dict = self._convert_contact_to_dict(contact_to_send)

                contact_result = await self.messenger.send_contact(
                    contact=contact_dict, recipient=user_id
                )

                contact_sent = contact_result.success

                if not contact_sent:
                    self.logger.error(f"Failed to send contact: {contact_result.error}")

                    # Send fallback text response
                    contact_name = self._extract_contact_name(contact_to_send)
                    fallback_text = f"👤 Contact echo - {contact_name} (relay failed)"
                    await self.messenger.send_text(
                        recipient=user_id, text=fallback_text
                    )

            # Update user activity
            await self.cache_helper.update_user_activity(user_id, "contact")

            # Store message in history
            await self.cache_helper.store_message_history(
                user_id,
                {
                    "message_id": message_id,
                    "type": "contact",
                    "contacts_count": len(contacts),
                    "timestamp": webhook.timestamp.isoformat(),
                    "echo_sent": contact_sent,
                },
            )

            processing_time = int((time.time() - start_time) * 1000)
            self.logger.info(f"✅ Contact message processed in {processing_time}ms")

            return {
                "success": True,
                "message_type": "contact",
                "metadata_sent": True,
                "contact_echoed": contact_sent,
                "contacts_count": len(contacts),
                "processing_time_ms": processing_time,
            }

        except Exception as e:
            self.logger.error(f"❌ Error handling contact message: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    async def handle_interactive_message(
        self, webhook: IncomingMessageWebhook, user_profile: UserProfile
    ) -> dict[str, any]:
        """
        Handle interactive message (button/list selections).

        Args:
            webhook: IncomingMessageWebhook with interactive message
            user_profile: User profile for tracking

        Returns:
            Result dictionary with operation status
        """
        try:
            start_time = time.time()

            user_id = webhook.user.user_id
            message_id = webhook.message.message_id
            selection_id = webhook.get_interactive_selection()

            self.logger.info(
                f"🔘 Processing interactive message from {user_id}: {selection_id}"
            )

            # Extract and format metadata
            metadata = MetadataExtractor.extract_metadata(webhook, start_time)
            metadata_text = MetadataExtractor.format_metadata_for_user(metadata)

            # Send metadata response
            metadata_result = await self.messenger.send_text(
                recipient=user_id, text=metadata_text, reply_to_message_id=message_id
            )

            if not metadata_result.success:
                self.logger.error(f"Failed to send metadata: {metadata_result.error}")
                return {"success": False, "error": "Failed to send metadata"}

            # Send acknowledgment of selection
            ack_text = f"✅ Interactive selection acknowledged: `{selection_id}`"
            await self.messenger.send_text(recipient=user_id, text=ack_text)

            # Update user activity
            await self.cache_helper.update_user_activity(user_id, "interactive")

            # Store message in history
            await self.cache_helper.store_message_history(
                user_id,
                {
                    "message_id": message_id,
                    "type": "interactive",
                    "selection_id": selection_id,
                    "timestamp": webhook.timestamp.isoformat(),
                    "processed": True,
                },
            )

            processing_time = int((time.time() - start_time) * 1000)
            self.logger.info(f"✅ Interactive message processed in {processing_time}ms")

            return {
                "success": True,
                "message_type": "interactive",
                "metadata_sent": True,
                "selection_acknowledged": True,
                "selection_id": selection_id,
                "processing_time_ms": processing_time,
            }

        except Exception as e:
            self.logger.error(
                f"❌ Error handling interactive message: {e}", exc_info=True
            )
            return {"success": False, "error": str(e)}

    def _convert_contact_to_dict(self, contact_obj) -> dict[str, any]:
        """Convert contact object to dictionary format for messenger."""
        contact_dict = {}

        # Extract name information
        if hasattr(contact_obj, "name") and contact_obj.name:
            name_obj = contact_obj.name
            contact_dict["name"] = {}

            if hasattr(name_obj, "formatted_name"):
                contact_dict["name"]["formatted_name"] = name_obj.formatted_name
            if hasattr(name_obj, "first_name"):
                contact_dict["name"]["first_name"] = name_obj.first_name
            if hasattr(name_obj, "last_name"):
                contact_dict["name"]["last_name"] = name_obj.last_name

        # Extract phone numbers
        if hasattr(contact_obj, "phones") and contact_obj.phones:
            phones = contact_obj.phones
            if not isinstance(phones, list):
                phones = [phones]
            contact_dict["phones"] = []
            for phone in phones:
                if hasattr(phone, "phone"):
                    phone_dict = {"phone": phone.phone}
                    if hasattr(phone, "type"):
                        phone_dict["type"] = phone.type
                    contact_dict["phones"].append(phone_dict)

        # Extract emails
        if hasattr(contact_obj, "emails") and contact_obj.emails:
            emails = contact_obj.emails
            if not isinstance(emails, list):
                emails = [emails]
            contact_dict["emails"] = []
            for email in emails:
                if hasattr(email, "email"):
                    email_dict = {"email": email.email}
                    if hasattr(email, "type"):
                        email_dict["type"] = email.type
                    contact_dict["emails"].append(email_dict)

        return contact_dict

    def _extract_contact_name(self, contact_obj) -> str:
        """Extract contact name for display."""
        if hasattr(contact_obj, "name") and contact_obj.name:
            name_obj = contact_obj.name
            if hasattr(name_obj, "formatted_name"):
                return name_obj.formatted_name
            elif hasattr(name_obj, "first_name"):
                first = name_obj.first_name or ""
                last = getattr(name_obj, "last_name", "") or ""
                return f"{first} {last}".strip()

        return "Unknown Contact"


# Convenience functions for direct use
async def handle_message_by_type(
    webhook: IncomingMessageWebhook,
    user_profile: UserProfile,
    messenger,
    cache_factory,
    logger,
) -> dict[str, any]:
    """
    Handle message based on its type (convenience function).

    Args:
        webhook: IncomingMessageWebhook to process
        user_profile: User profile for tracking
        messenger: IMessenger instance
        cache_factory: Cache factory
        logger: Logger instance

    Returns:
        Result dictionary
    """
    handlers = MessageHandlers(messenger, cache_factory, logger)
    message_type = webhook.get_message_type_name().lower()

    if message_type == "text":
        return await handlers.handle_text_message(webhook, user_profile)
    elif message_type in ["image", "video", "audio", "voice", "document", "sticker"]:
        return await handlers.handle_media_message(webhook, user_profile)
    elif message_type == "location":
        return await handlers.handle_location_message(webhook, user_profile)
    elif message_type in ["contact", "contacts"]:
        return await handlers.handle_contact_message(webhook, user_profile)
    elif message_type == "interactive":
        return await handlers.handle_interactive_message(webhook, user_profile)
    else:
        logger.warning(f"Unsupported message type: {message_type}")
        return {"success": False, "error": f"Unsupported message type: {message_type}"}
