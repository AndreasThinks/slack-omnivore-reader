# Slack Omnivore Integration

This application integrates Slack with Omnivore, allowing you to save URLs shared in Slack to your Omnivore account.

[![Deploy](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/AndreasThinks/slack-omnivore-reader)

## Features
- Saves URLs shared in Slack to Omnivore
- Applies custom labels to saved articles
- Configurable rate limiting
- Secure handling of environment variables

## Deployment
Click the "Deploy to Heroku" button above to start the deployment process. Don't worry if you don't have all of these yet, you'll get the rest after deploying your Slack App.

- `SLACK_BOT_TOKEN`: Your Slack Bot Token
- `SLACK_SIGNING_SECRET`: Your Slack Signing Secret
- `OMNIVORE_API_KEY`: Your Omnivore API Key
- `ALLOWED_HOSTS`: Comma-separated list of allowed hosts (e.g., your-app-name.herokuapp.com)
- `OMNIVORE_LABEL`: (Optional) Label to apply to saved articles in Omnivore
- `RATE_LIMIT_PER_MINUTE`: (Optional) Number of requests allowed per minute

## Installation
To add the application to Slack, you *must* have deployed the back-end on Heroku using the process above.

Once this is complete, you can create an application on your [Slack workspace](https://api.slack.com/) (you will need administrator permissions). You can either use our [Slack Manifest](manifest.json), or follow the manual steps below.

- In the "oAuth & Permissions" section, enable **channels:history**, **chat:write** and **reactions:read**, and obtain your SLACK_BOT_TOKEN.
- In the "Event Subscriptions" section, add "reaction_added" to bot events

Once your bot has been installed, follow the configuration steps below.

- In the "Event Subscriptions" section, add your full Heroku application URL (in the format https://your-heroku-app.herokuapp.com/slack/events) as the request URL. 
- If you do not already have one, create an [Omnivore](https://omnivore.app/) account, and [get an API key](https://omnivore.app/settings/api).
- From the Heroku web-interface, add all environment variables to your application.
- From within your Slack client, add your bot to a channel by sending them a DM

That's it!  Test it by reacting to a post with a valid URL. You should be able to see the event in your Heroku logs, and it will appear in your Omnivore library.

## Local Development
1. Clone this repository
2. Create a `.env` file with the required environment variables
3. Install dependencies: `pip install -r requirements.txt`
4. Run the application: `python app.py`

## Contributing
Contributions are welcome! Please feel free to submit a Pull Request.

## License
This project is licensed under the apache 2.0 license.
