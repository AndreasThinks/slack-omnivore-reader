# Slack Omnivore Integration

This application integrates Slack with Omnivore, allowing you to save URLs shared in Slack to your Omnivore account.

[![Deploy](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/AndreasThinks/slack-omnivore-reader)

<a href="https://slack.com/oauth/v2/authorize?scope=channels%3Ahistory%2Cchat%3Awrite%2Creactions%3Aread&amp;user_scope=&amp;redirect_uri=https%3A%2F%2Fandreasthinks.github.io%2Fslack-omnivore-reader%2Finstall&amp;client_id=3467318693601.7333656737985" style="align-items:center;color:#000;background-color:#fff;border:1px solid #ddd;border-radius:4px;display:inline-flex;font-family:Lato, sans-serif;font-size:16px;font-weight:600;height:48px;justify-content:center;text-decoration:none;width:236px"><svg xmlns="http://www.w3.org/2000/svg" style="height:20px;width:20px;margin-right:12px" viewBox="0 0 122.8 122.8"><path d="M25.8 77.6c0 7.1-5.8 12.9-12.9 12.9S0 84.7 0 77.6s5.8-12.9 12.9-12.9h12.9v12.9zm6.5 0c0-7.1 5.8-12.9 12.9-12.9s12.9 5.8 12.9 12.9v32.3c0 7.1-5.8 12.9-12.9 12.9s-12.9-5.8-12.9-12.9V77.6z" fill="#e01e5a"></path><path d="M45.2 25.8c-7.1 0-12.9-5.8-12.9-12.9S38.1 0 45.2 0s12.9 5.8 12.9 12.9v12.9H45.2zm0 6.5c7.1 0 12.9 5.8 12.9 12.9s-5.8 12.9-12.9 12.9H12.9C5.8 58.1 0 52.3 0 45.2s5.8-12.9 12.9-12.9h32.3z" fill="#36c5f0"></path><path d="M97 45.2c0-7.1 5.8-12.9 12.9-12.9s12.9 5.8 12.9 12.9-5.8 12.9-12.9 12.9H97V45.2zm-6.5 0c0 7.1-5.8 12.9-12.9 12.9s-12.9-5.8-12.9-12.9V12.9C64.7 5.8 70.5 0 77.6 0s12.9 5.8 12.9 12.9v32.3z" fill="#2eb67d"></path><path d="M77.6 97c7.1 0 12.9 5.8 12.9 12.9s-5.8 12.9-12.9 12.9-12.9-5.8-12.9-12.9V97h12.9zm0-6.5c-7.1 0-12.9-5.8-12.9-12.9s5.8-12.9 12.9-12.9h32.3c7.1 0 12.9 5.8 12.9 12.9s-5.8 12.9-12.9 12.9H77.6z" fill="#ecb22e"></path></svg>Add to Slack</a>

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
This project is licensed under the apache 2.0 license.
