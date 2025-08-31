# 🚂 Railway Deployment Guide - Wappa Full Example

Simple and fast deployment of your Wappa WhatsApp Business application to Railway.app

## 🚀 Quick Railway Deployment

### 1. Prerequisites

- Railway CLI installed: `npm install -g @railway/cli`
- Railway account: [railway.app](https://railway.app)
- WhatsApp Business API credentials

### 2. One-Command Deployment

```bash
# Deploy to Railway
railway up

# Follow the prompts to create a new project
```

## ⚙️ Environment Variables Setup

After deployment, configure these environment variables in Railway Dashboard:

### Required Variables

```bash
# WhatsApp Business API
WP_ACCESS_TOKEN=your_access_token_here
WP_PHONE_ID=your_phone_number_id_here
WP_BID=your_business_id_here
WHATSAPP_WEBHOOK_VERIFY_TOKEN=your_webhook_token_here

# Redis (if using Railway Redis plugin)
REDIS_URL=redis://redis.railway.internal:6379

# Optional: AI Integration
OPENAI_API_KEY=your_openai_key_here
```

### Railway Auto-Set Variables

Railway automatically configures:
- `PORT` - Dynamic port assignment
- `RAILWAY_ENVIRONMENT` - Environment detection
- Domain and SSL certificates

## 📡 Adding Redis

### Option 1: Railway Redis Plugin

```bash
# Add Redis plugin via CLI
railway add --plugin redis

# Or via Railway Dashboard:
# Project → Plugins → Add Redis
```

### Option 2: External Redis

Set `REDIS_URL` to your external Redis provider:
```bash
# Redis Cloud
REDIS_URL=redis://username:password@redis-host:port

# AWS ElastiCache
REDIS_URL=rediss://cache-cluster.amazonaws.com:6380

# Upstash Redis
REDIS_URL=rediss://username:password@host:port
```

## 🔗 Webhook Configuration

After deployment, configure your WhatsApp webhook:

1. **Get your Railway URL**: `https://your-app-name.up.railway.app`

2. **Set webhook in Facebook Developer Console**:
   ```
   Webhook URL: https://your-app-name.up.railway.app/webhook/messenger/YOUR_PHONE_ID/whatsapp
   Verify Token: your_webhook_token_here
   ```

3. **Test webhook**:
   ```bash
   curl "https://your-app-name.up.railway.app/health"
   ```

## 📋 Step-by-Step Setup

### Step 1: Login to Railway

```bash
railway login
```

### Step 2: Initialize Project

```bash
# In your wappa_full_example directory
railway init

# Select "Create new project"
# Choose a project name
```

### Step 3: Deploy

```bash
railway up
```

### Step 4: Configure Environment

```bash
# Set variables via CLI
railway variables set WP_ACCESS_TOKEN=your_token
railway variables set WP_PHONE_ID=your_phone_id
railway variables set WP_BID=your_business_id
railway variables set WHATSAPP_WEBHOOK_VERIFY_TOKEN=your_webhook_token

# Or use Railway Dashboard for easier management
```

### Step 5: Add Redis

```bash
# Add Redis plugin
railway add redis

# Redis URL will be auto-configured as:
# REDIS_URL=redis://redis.railway.internal:6379
```

### Step 6: Configure Custom Domain (Optional)

```bash
# Add custom domain
railway domain

# Or via Dashboard: Settings → Domains
```

## 🔍 Monitoring & Debugging

### View Logs

```bash
# Real-time logs
railway logs

# Or via Railway Dashboard: Deployments → View Logs
```

### Health Checks

```bash
# Check application health
curl https://your-app.up.railway.app/health

# Detailed health check
curl https://your-app.up.railway.app/health/detailed
```

### Environment Info

```bash
# List all variables
railway variables

# Show deployment info
railway status
```

## 🛠️ Development Workflow

### Local Development

```bash
# Link to Railway project
railway link

# Pull environment variables
railway run --service your-service-name

# Start local development
uv run python -m app.main
```

### Deploy Updates

```bash
# Deploy latest changes
railway up

# Or enable auto-deploy via GitHub integration
```

## 📊 Scaling on Railway

Railway automatically handles:
- **Auto-scaling**: Based on CPU/memory usage
- **Load balancing**: Multiple instance management
- **SSL certificates**: Automatic HTTPS
- **CDN**: Global edge caching

### Manual Scaling

```bash
# Scale replicas (Pro plan required)
railway scale --replicas 3
```

## 🚨 Troubleshooting

### Common Issues

#### 1. Build Fails

```bash
# Check build logs
railway logs --deployment

# Common fixes:
# - Ensure Dockerfile is optimized
# - Check uv.lock exists
# - Verify Python version compatibility
```

#### 2. Environment Variables Missing

```bash
# Check current variables
railway variables

# Set missing variables
railway variables set VARIABLE_NAME=value
```

#### 3. Redis Connection Issues

```bash
# Verify Redis plugin is added
railway plugins

# Check Redis URL format
railway variables get REDIS_URL
```

#### 4. Webhook Not Working

```bash
# Check application logs
railway logs

# Verify webhook URL format:
# https://your-app.up.railway.app/webhook/messenger/PHONE_ID/whatsapp

# Test webhook endpoint
curl -X GET "https://your-app.up.railway.app/webhook/messenger/YOUR_PHONE_ID/whatsapp?hub.verify_token=YOUR_TOKEN&hub.challenge=test"
```

## 💰 Railway Pricing Considerations

### Hobby Plan (Free Tier)
- $5 credit/month
- 21 days uptime limit per month
- 1GB RAM, 1 vCPU
- Perfect for development/testing

### Pro Plan ($20/month)
- No usage limits
- Custom domains
- Multiple environments
- Priority support
- Auto-scaling

## 🔒 Security Best Practices

### Environment Variables
- Never commit sensitive data to Git
- Use Railway's encrypted environment variables
- Rotate access tokens regularly

### Access Control
- Enable two-factor authentication
- Use team management for collaboration
- Set up deployment notifications

## 📚 Useful Railway Commands

```bash
# Project management
railway init          # Initialize new project
railway link          # Link to existing project
railway unlink        # Unlink from project

# Deployment
railway up            # Deploy application
railway logs          # View application logs
railway status        # Show deployment status

# Environment
railway variables     # List all variables
railway variables set KEY=value  # Set variable
railway variables delete KEY     # Delete variable

# Services
railway add redis     # Add Redis plugin
railway remove redis  # Remove Redis plugin

# Domains
railway domain        # Manage custom domains
railway open          # Open deployed application
```

## 🎯 Webhook URLs for WhatsApp

After Railway deployment, use these URLs:

```bash
# Primary webhook URL
https://your-app.up.railway.app/webhook/messenger/YOUR_PHONE_ID/whatsapp

# Health check
https://your-app.up.railway.app/health

# API documentation
https://your-app.up.railway.app/docs
```

## ✅ Deployment Checklist

### Pre-Deployment
- [ ] Railway CLI installed and authenticated
- [ ] WhatsApp Business API credentials ready
- [ ] Project tested locally

### Deployment
- [ ] `railway up` completed successfully
- [ ] All environment variables configured
- [ ] Redis plugin added (if needed)
- [ ] Application health check passes

### Post-Deployment
- [ ] WhatsApp webhook configured and verified
- [ ] Test message flow end-to-end
- [ ] Interactive commands working (buttons, lists)
- [ ] Monitoring and alerting configured

## 🆘 Getting Help

- **Railway Docs**: [docs.railway.app](https://docs.railway.app)
- **Railway Discord**: [discord.gg/railway](https://discord.gg/railway)
- **Wappa Framework**: [wappa.mimeia.com](https://wappa.mimeia.com)

---

**🚂 Your Wappa app is now live on Railway!**

Railway provides the easiest path to production for your WhatsApp Business application with automatic scaling, SSL, and global CDN.

**Built with ❤️ using the Wappa Framework**