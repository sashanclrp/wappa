"""Interactive message demonstrations.

These two examples used to be mounted as production HTTP routes
(``/interactive/send-complex-buttons`` and ``/interactive/send-menu-list``).
They are demonstration content, not runtime capabilities, so they now live
here as plain Messenger calls a handler can invoke.
"""

from __future__ import annotations

from wappa.domain.interfaces.messaging_interface import IMessenger
from wappa.messaging.whatsapp.models.basic_models import MessageResult
from wappa.messaging.whatsapp.models.interactive_models import (
    HeaderType,
    InteractiveHeader,
    ListRow,
    ListSection,
    ReplyButton,
)


async def send_complex_button_demo(
    messenger: IMessenger, recipient: str
) -> MessageResult:
    """Button message with a text header, three buttons, and a footer."""
    buttons = [
        ReplyButton(id="yes_button", title="Yes"),
        ReplyButton(id="no_button", title="No"),
        ReplyButton(id="maybe_button", title="Maybe"),
    ]
    header = InteractiveHeader(type=HeaderType.TEXT, text="Quick Decision Required")
    return await messenger.send_button_message(
        buttons=buttons,
        recipient=recipient,
        body=(
            "Would you like to proceed with this action? "
            "Please choose one of the options below."
        ),
        header=header,
        footer="This message will expire in 24 hours",
    )


async def send_menu_list_demo(messenger: IMessenger, recipient: str) -> MessageResult:
    """Restaurant-style list message with three sections."""
    sections = [
        ListSection(
            title="Main Dishes",
            rows=[
                ListRow(
                    id="pizza_margherita",
                    title="Pizza Margherita",
                    description="Classic tomato and mozzarella - $12.99",
                ),
                ListRow(
                    id="pasta_carbonara",
                    title="Pasta Carbonara",
                    description="Creamy bacon pasta - $14.99",
                ),
            ],
        ),
        ListSection(
            title="Salads",
            rows=[
                ListRow(
                    id="caesar_salad",
                    title="Caesar Salad",
                    description="Crispy romaine with parmesan - $8.99",
                ),
                ListRow(
                    id="greek_salad",
                    title="Greek Salad",
                    description="Fresh vegetables with feta - $9.99",
                ),
            ],
        ),
        ListSection(
            title="Beverages",
            rows=[
                ListRow(
                    id="coke",
                    title="Coca Cola",
                    description="Classic refreshing cola - $2.99",
                ),
                ListRow(
                    id="water",
                    title="Sparkling Water",
                    description="Refreshing mineral water - $1.99",
                ),
            ],
        ),
    ]
    return await messenger.send_list_message(
        sections=sections,
        recipient=recipient,
        body=(
            "Welcome to our restaurant! Browse our menu and select what "
            "you'd like to order."
        ),
        button_text="View Menu",
        header="Restaurant Menu",
        footer="Prices include tax - Free delivery over $25",
    )
