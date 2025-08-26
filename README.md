# wappa
Open Source Framework to develop smart Workflows, Agents and full chat appllications through WhatsApp

So the idea of this project is to take the /app and refactor it to break this up and make it into an opensource project for example things I want: 
1) from wapp import WhatsAppMessenger -> So then throughoutt flow in /events I can just initialize the WhatsAppMessenger and send all the messages
2) have a terminal like ruff or black named wappa so when the user writes uvx wappa init or uv run wappa init a terminal opens to generate a clean project

and yeah I mean right now I have in this project, Airtable, Payment processor I want to delete does services and payment webhooks... just stick with the WhatsApp webhooks and the Messenger interface, have the event_dispatcher as the final destination of all webhooks... and literally All i want when the client hits init is just the webhooks dispatching to the eventhandler all the other folders and scaffolding shoudl be imported through the Wappa module!

so yeah the purpose of this project is this