# TradingAgents Service Deployment on Railway.com

This guide explains how to deploy the TradingAgents service on Railway.com.

## Prerequisites

1. A Railway.com account
2. A GitHub account (to fork this repository)
3. API keys for the LLM providers you want to use

## Deployment Steps

### 1. Fork the Repository

First, fork this repository to your GitHub account:
1. Go to https://github.com/nordmindi/vein-reports
2. Click the "Fork" button
3. Follow the prompts to create your fork

### 2. Deploy to Railway

1. Go to https://railway.app/
2. Sign in to your account
3. Click "New Project"
4. Select "Deploy from GitHub"
5. Choose your forked repository
6. Railway will automatically detect the project and use the `Dockerfile.service` file

### 3. Configure Environment Variables

After deployment, configure the following environment variables in Railway:

1. Go to your Railway project
2. Click on the "Settings" tab
3. Click on "Variables"
4. Add the following variables:

| Variable | Description | Example Value |
|----------|-------------|---------------|
| `TRADINGAGENTS_SERVICE_API_KEY` | API key for service authentication | `your-secret-api-key` |
| `OPENAI_API_KEY` | OpenAI API key (if using OpenAI models) | `sk-...` |
| `GOOGLE_API_KEY` | Google API key (if using Google models) | `AIza...` |
| `HOST` | Host to bind the service to | `0.0.0.0` |
| `PORT` | Port to listen on | `8000` |

### 4. Redeploy

After setting the environment variables, Railway will automatically redeploy the application.

## Troubleshooting

### Common Issues

1. **Application crashes on startup**
   - Ensure `TRADINGAGENTS_SERVICE_API_KEY` is set
   - Check that the correct Dockerfile is being used (`Dockerfile.service`)

2. **Health checks failing**
   - Check the logs for error messages
   - Ensure the service is binding to `0.0.0.0` and not `127.0.0.1`

3. **LLM API errors**
   - Verify your API keys are correct
   - Check that you have credits/balance on your LLM provider accounts

### Viewing Logs

To view logs in Railway:
1. Go to your Railway project
2. Click on the "Deployments" tab
3. Select the latest deployment
4. Click on "View Logs"

## API Usage

Once deployed, you can access the API at your Railway URL:

```
# Health check
GET https://your-railway-url.railway.app/health

# Create report job
POST https://your-railway-url.railway.app/v1/reports
Headers:
  X-API-Key: your-api-key
  Content-Type: application/json
Body:
  {
    "ticker": "NVDA",
    "analysis_date": "2026-05-07",
    "selected_analysts": ["market", "news", "fundamentals"]
  }
```

## Scaling

Railway automatically scales your application based on traffic. For high-traffic applications, you may want to:

1. Increase the number of workers by setting `TRADINGAGENTS_SERVICE_WORKERS` environment variable
2. Monitor memory usage and adjust instance size if needed
3. Consider rate limits of your LLM providers

## Security Considerations

1. Always use a strong API key for `TRADINGAGENTS_SERVICE_API_KEY`
2. Store API keys securely in Railway's environment variables
3. Use HTTPS (Railway provides this automatically)
4. Regularly rotate your API keys