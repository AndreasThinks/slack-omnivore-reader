# Slack Omnivore Integration

This application integrates Slack with Omnivore, allowing you to save URLs shared in Slack to your Omnivore account.

[![Deploy](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/AndreasThinks/slack-omnivore-reader)

## Features
- Saves URLs shared in Slack to Omnivore
- Applies custom labels to saved articles
- Configurable rate limiting
- Secure handling of environment variables

## Deployment
Click the "Deploy to Heroku" button above to start the deployment process. You'll need to provide the following environment variables:

- `SLACK_BOT_TOKEN`: Your Slack Bot Token
- `SLACK_SIGNING_SECRET`: Your Slack Signing Secret
- `OMNIVORE_API_KEY`: Your Omnivore API Key
- `ALLOWED_HOSTS`: Comma-separated list of allowed hosts (e.g., your-app-name.herokuapp.com)
- `OMNIVORE_LABEL`: (Optional) Label to apply to saved articles in Omnivore
- `RATE_LIMIT_PER_MINUTE`: (Optional) Number of requests allowed per minute

## Local Development
1. Clone this repository
2. Create a `.env` file with the required environment variables
3. Install dependencies: `pip install -r requirements.txt`
4. Run the application: `python app.py`

## Contributing
Contributions are welcome! Please feel free to submit a Pull Request.

## License
This project is licensed under the MIT License.