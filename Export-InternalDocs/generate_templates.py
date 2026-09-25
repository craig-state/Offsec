#!/usr/bin/env python3
"""
Standalone Template Generator with Auto-Domain Detection
==========================================================

Generates hundreds of thousands of unique templates for embedding inversion
attacks. Includes automatic domain detection from target embeddings.

This is a standalone script — no other project files required.

Requirements (pip):
    pip install numpy
    pip install torch transformers    (only needed for --auto-detect from embeddings)

Usage:
    # Auto-detect domain from embeddings, generate 100k templates
    python generate_templates.py embeddings2.npy -o templates.json

    # Auto-detect from a specific chunk
    python generate_templates.py embeddings2.npy --chunk 3 -o templates.json

    # Majority vote across first 5 chunks
    python generate_templates.py embeddings2.npy --chunks 0,1,2,3,4 -o templates.json

    # Custom count
    python generate_templates.py embeddings2.npy --count 500000 -o templates.json

    # Skip detection, specify domain manually
    python generate_templates.py --domain infrastructure_credentials -o templates.json

    # Generate for specific chunk position (first/middle/last)
    python generate_templates.py --domain it_password --chunk-position first -o templates.json

    # List available domains
    python generate_templates.py --list-domains

Then use the output with the attack tools:
    python emb_seeds_fin.py embeddings2.npy --chunk 0 \\
        --templates templates.json --fill-slots --wordlist passwords.txt
    python emb_unified_fin.py embeddings2.npy --chunk 0 \\
        --templates templates.json --wordlist passwords.txt
"""

import re
import sys
import json
import random
import hashlib
import argparse
import numpy as np
from itertools import product, permutations, combinations
from typing import List, Dict, Set, Generator, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict, Counter
from pathlib import Path


# ============================================================================
# COMPREHENSIVE VARIATION BANKS
# ============================================================================

# Password/credential terminology across languages and styles
PASSWORD_TERMS = {
    "standard": [
        "password", "passcode", "pass code", "credential", "access code",
        "security code", "auth code", "authentication code", "PIN",
        "secret", "passphrase", "pass phrase", "access key"
    ],
    "technical": [
        "passwd", "pwd", "cred", "auth token", "secret key", "API key",
        "bearer token", "access token", "refresh token", "session key"
    ],
    "formal": [
        "authentication credential", "security credential",
        "access credential", "login credential", "user credential"
    ],
    "casual": [
        "pw", "pass", "login", "key", "code"
    ],
    "temporary": [
        "temporary password", "temp password", "one-time password",
        "OTP", "initial password", "default password", "reset password",
        "new password", "generated password", "assigned password"
    ]
}

# URL/endpoint terminology
URL_TERMS = {
    "standard": [
        "URL", "link", "website", "web address", "address",
        "site", "web site", "webpage", "web page"
    ],
    "technical": [
        "endpoint", "API endpoint", "service URL", "base URL",
        "host", "server", "destination", "target URL", "URI"
    ],
    "portal": [
        "portal", "login portal", "access portal", "web portal",
        "user portal", "employee portal", "admin portal", "SSO portal"
    ],
    "casual": [
        "page", "login page", "site", "the link"
    ]
}

# Action/instruction verbs
ACTION_VERBS = {
    "navigation": [
        "navigate to", "go to", "visit", "access", "open",
        "proceed to", "head to", "click on", "follow"
    ],
    "formal": [
        "please navigate to", "kindly visit", "please access",
        "you are requested to visit", "please proceed to"
    ],
    "casual": [
        "go", "click", "open up", "check out", "hit"
    ],
    "technical": [
        "connect to", "access endpoint", "authenticate at",
        "login to", "sign in at", "authenticate via"
    ]
}

# Reset/help action phrases
RESET_ACTIONS = [
    "Need help signing in", "Forgot password", "Reset password",
    "Can't access your account", "Sign in help", "Account recovery",
    "Unlock account", "Password assistance", "Login help",
    "Trouble signing in", "Account access", "Security reset",
    "Password reset", "Forgot your password", "Reset your password",
    "Having trouble signing in", "Account locked", "Need password help",
    "Lost password", "Recover account", "Regain access"
]

# Immediacy/urgency terms
IMMEDIACY_TERMS = [
    "immediately", "right away", "promptly", "at once",
    "as soon as possible", "ASAP", "without delay", "urgently",
    "now", "straight away", "right now", "", "upon first login",
    "on first access", "after logging in",
    "on your first login", "on your next login",
    "before your next session", "at your first opportunity",
]

# Formality prefixes
FORMALITY_PREFIXES = [
    "", "Please ", "Kindly ", "We request that you ",
    "You are required to ", "You must ", "You should ",
    "We ask that you ", "It is required that you ",
    "For security purposes, ", "For your security, ",
    "Important: ", "Action required: ", "Notice: "
]

# Sentence connectors
CONNECTORS = [
    "and", "then", "after which", "following which",
    "and then", "next", "subsequently", "afterward",
    ". Then", ". After that,", ". Next,"
]

# Closing phrases
CLOSING_PHRASES = [
    ".", "!", " immediately.", " right away.",
    " as soon as possible.", " upon first login.",
    " on your next login.", " within 24 hours.",
    " before it expires.", " to complete setup.",
    " which must be changed immediately.",
    " which must be updated on first login.",
    " and must be changed immediately.",
    " and must be updated on first login.",
    " which expires in 24 hours.",
]

# Time constraints
TIME_CONSTRAINTS = [
    "", "within 24 hours", "within 48 hours", "within 7 days",
    "before expiration", "on first login", "immediately",
    "by end of day", "at your earliest convenience"
]

# Database/service type terminology
DBTYPE_TERMS = [
    "Production database", "Database", "Production DB", "MySQL",
    "PostgreSQL", "Postgres", "MongoDB", "Redis", "MariaDB", "SQL Server",
    "Oracle", "MSSQL", "SQLite", "Cassandra", "DynamoDB", "CouchDB",
    "Staging database", "Dev database", "Test database",
    "Primary database", "Replica database", "Master database",
]

# Service/system names
SERVICE_TERMS = [
    "Production database server", "Database server", "DB server",
    "Production server", "Staging server", "Application server",
    "Web server", "API server", "Backend server", "Auth server",
    "LDAP server", "SMTP server", "FTP server", "SSH gateway",
    "VPN gateway", "Kubernetes cluster", "Docker registry",
    "Jenkins", "GitLab", "Grafana", "Prometheus", "Elasticsearch",
    "RabbitMQ", "Kafka", "Nginx", "Apache", "Tomcat",
    "Admin panel", "Control panel", "Management console",
    "AWS console", "Azure portal", "GCP console",
]

# Username terms for infrastructure contexts
USERNAME_TERMS = [
    "admin", "root", "administrator", "sa", "postgres", "mysql",
    "dbadmin", "sysadmin", "devops", "deploy", "service", "app",
    "backup", "monitor", "readonly", "readwrite", "superuser",
    "operator", "maintainer", "support", "guest", "test",
]

# Hostname / IP terms
HOSTNAME_TERMS = [
    "db-prod-01", "db-prod-02", "db-staging-01", "app-prod-01",
    "web-prod-01", "api-prod-01", "srv-01", "node-01", "master-01",
    "10.0.0.1", "10.0.1.100", "192.168.1.10", "172.16.0.50",
    "db.internal.corp", "prod-db.company.local", "api.internal.net",
]

# Connection context phrases for infrastructure credentials
INFRA_CONTEXT_PHRASES = [
    "server admin username is", "admin username is", "username is",
    "login username is", "default username is", "root user is",
    "admin user is", "service account is", "system user is",
    "db user is", "database user is", "connection user is",
]

# Credential joining phrases
CREDENTIAL_JOINERS = [
    "with password", "password", "and password is", "pass",
    "and the password is", "pwd", "password is", "with pass",
    "with credential", "using password", "authenticated by",
    "with secret", "and password", "/ password",
]

# Cloud - AWS
AWS_SERVICES = [
    "S3", "EC2", "Lambda", "RDS", "DynamoDB", "IAM", "EKS", "ECS",
    "CloudFront", "SQS", "SNS", "SES", "Redshift", "ElastiCache",
    "Secrets Manager", "Parameter Store", "CloudWatch", "Route 53",
]

AWS_REGIONS = [
    "us-east-1", "us-west-2", "eu-west-1", "eu-central-1",
    "ap-southeast-1", "ap-northeast-1", "us-east-2", "ca-central-1",
]

# Cloud - Azure
AZURE_SERVICES = [
    "Azure AD", "Azure SQL", "Azure Blob Storage", "Azure Functions",
    "AKS", "Azure DevOps", "Key Vault", "Cosmos DB", "Azure App Service",
    "Azure Service Bus", "Azure Event Hub", "Azure Storage",
]

AZURE_RESOURCE_TYPES = [
    "subscription", "resource group", "storage account", "SQL database",
    "key vault", "app registration", "service principal", "managed identity",
]

# Network / VPN
VPN_TYPES = [
    "OpenVPN", "WireGuard", "IPSec", "Cisco AnyConnect", "FortiClient",
    "GlobalProtect", "Pulse Secure", "F5 BIG-IP", "Palo Alto",
]

WIFI_SECURITY = ["WPA2-Enterprise", "WPA3", "WPA2-PSK", "802.1X"]

NETWORK_DEVICES = [
    "firewall", "router", "switch", "access point", "load balancer",
    "VPN concentrator", "proxy", "WAF", "IDS/IPS",
]

# CI/CD DevOps
CICD_PLATFORMS = [
    "GitHub Actions", "Jenkins", "GitLab CI", "CircleCI", "Travis CI",
    "Azure Pipelines", "Terraform Cloud", "ArgoCD", "Ansible Tower",
    "Bamboo", "TeamCity", "Drone CI",
]

REGISTRY_TYPES = [
    "Docker Hub", "ECR", "GCR", "ACR", "GitHub Container Registry",
    "Harbor", "Nexus", "Artifactory", "Quay.io",
]

# Email / SMTP
SMTP_SERVERS = [
    "smtp.gmail.com", "smtp.office365.com", "smtp.sendgrid.net",
    "email-smtp.us-east-1.amazonaws.com", "smtp.mailgun.org",
    "smtp-relay.sendinblue.com", "smtp.postmarkapp.com",
    "smtp.company.com", "mail.internal.corp",
]

EMAIL_PROTOCOLS = ["SMTP", "IMAP", "POP3", "Exchange", "MAPI"]

# Financial / Banking
BANK_NAMES = [
    "Chase", "Bank of America", "Wells Fargo", "Citibank", "Goldman Sachs",
    "JP Morgan", "Morgan Stanley", "HSBC", "Barclays", "Deutsche Bank",
    "First National", "Silicon Valley Bank", "Capital One",
]

TRANSACTION_TYPES = [
    "wire transfer", "ACH transfer", "SWIFT transfer", "domestic wire",
    "international wire", "direct deposit", "payment", "disbursement",
]

# Legal
LEGAL_TYPES = [
    "NDA", "Non-Disclosure Agreement", "Settlement Agreement",
    "Master Services Agreement", "SLA", "SOW", "License Agreement",
    "Employment Agreement", "Non-Compete", "Merger Agreement",
    "Asset Purchase Agreement", "Stock Purchase Agreement",
]

LEGAL_PARTIES = [
    "the Company", "the Vendor", "the Contractor", "the Employee",
    "the Acquiring Party", "the Target", "the Licensee", "the Licensor",
]

# Medical / HIPAA
MEDICAL_FACILITIES = [
    "General Hospital", "Medical Center", "Regional Health System",
    "Community Clinic", "Urgent Care", "Specialty Clinic",
    "Children's Hospital", "Veterans Medical Center",
]

DIAGNOSIS_CODES = [
    "ICD-10: {CODE}", "CPT: {CODE}", "diagnosis code {CODE}",
    "DRG: {CODE}", "procedure code {CODE}",
]

MEDICAL_DEPARTMENTS = [
    "Cardiology", "Oncology", "Orthopedics", "Neurology", "Radiology",
    "Emergency", "Internal Medicine", "Surgery", "Pediatrics", "ICU",
]

# Customer PII
PII_DOCUMENT_TYPES = [
    "customer record", "account profile", "user record",
    "member profile", "subscriber record", "client file",
]

# Internal Strategy
MEETING_TYPES = [
    "Board meeting", "Executive committee", "Strategy session",
    "Quarterly business review", "Leadership offsite", "Budget meeting",
    "M&A committee", "Risk committee", "Compensation committee",
]

STRATEGY_ACTIONS = [
    "approved", "discussed", "proposed", "tabled", "voted on",
    "greenlit", "postponed", "finalized", "rejected", "escalated",
]

# Certificate / TLS
CERT_TYPES = [
    "SSL", "TLS", "wildcard SSL", "EV SSL", "code signing",
    "client certificate", "intermediate CA", "root CA", "self-signed",
]

CERT_FORMATS = ["PEM", "DER", "PKCS12", "P7B", "PFX", "JKS"]

# Encryption / Secrets
ENCRYPTION_TYPES = [
    "AES-256", "RSA-4096", "GPG", "PGP", "KMS", "HSM",
    "Vault", "SOPS", "age", "LUKS", "BitLocker",
]

VAULT_PATHS = [
    "secret/data/production", "secret/data/staging", "kv/production",
    "secret/infra/database", "secret/app/api-keys", "transit/keys/main",
]

# OAuth / SSO
OAUTH_PROVIDERS = [
    "Okta", "Auth0", "Azure AD", "Google Workspace", "OneLogin",
    "PingIdentity", "Keycloak", "AWS Cognito", "ForgeRock", "Duo",
]

OAUTH_GRANT_TYPES = [
    "authorization_code", "client_credentials", "implicit",
    "password", "refresh_token", "device_code",
]

# Vendor / Partner
VENDOR_NAMES = [
    "Acme Corp", "TechVendor Inc", "CloudPartner LLC", "DataCorp",
    "SecureNet", "InfoSys", "GlobalTech", "NextGen Solutions",
    "PlatformOne", "ServicePro",
]

# SaaS Platforms
SAAS_PLATFORMS = [
    "Salesforce", "Jira", "Confluence", "Slack", "Microsoft Teams",
    "ServiceNow", "Workday", "Datadog", "Splunk", "PagerDuty",
    "Zendesk", "HubSpot", "Snowflake", "Tableau", "Okta",
    "GitHub Enterprise", "Bitbucket", "New Relic",
]


# ============================================================================
# TEMPLATE PATTERN STRUCTURES
# ============================================================================

# Structural patterns for password reset templates
PASSWORD_RESET_PATTERNS = [
    # Standard patterns
    "{PREFIX}{VERB} {URL}. {PW_CONTEXT} {PASSWORD}{CLOSING}",
    "{PREFIX}{VERB} {URL} and {ACTION}. {PW_CONTEXT} {PASSWORD}{CLOSING}",
    "{PW_CONTEXT} {PASSWORD}. {PREFIX}{VERB} {URL}{CLOSING}",
    "{PREFIX}use {PASSWORD} to {VERB} {URL}{CLOSING}",
    "{ACTION} at {URL}. {PW_CONTEXT} {PASSWORD}{CLOSING}",

    # Short/compact patterns
    "{PW_TERM}: {PASSWORD}. {URL_TERM}: {URL}",
    "{URL_TERM}: {URL} | {PW_TERM}: {PASSWORD}",
    "Login: {URL}, {PW_TERM}: {PASSWORD}",
    "{URL} - {PW_TERM} {PASSWORD}",
    "Access {URL} with {PASSWORD}",

    # Technical patterns
    "AUTH_URL={URL} PASSWD={PASSWORD}",
    "Endpoint: {URL}, Token: {PASSWORD}",
    "Service credentials - URL: {URL}, Key: {PASSWORD}",

    # Multi-sentence patterns
    "{PREFIX}{VERB} {URL}. Click on {ACTION}. {PW_CONTEXT} {PASSWORD}{CLOSING}",
    "{PW_CONTEXT} {PASSWORD}. This must be changed {IMMEDIACY}. {VERB} {URL}.",
    "Your account has been reset. {PW_CONTEXT} {PASSWORD}. {PREFIX}{VERB} {URL}{CLOSING}",

    # Question-answer style
    "How to reset? {VERB} {URL}, use {PASSWORD}.",
    "Lost access? {PREFIX}{VERB} {URL}. {PW_TERM}: {PASSWORD}.",

    # Instructional style
    "Step 1: {VERB} {URL}. Step 2: Enter {PASSWORD}. Step 3: Change {IMMEDIACY}.",
    "To reset your password: {VERB} {URL} and use {PASSWORD}.",

    # "which must be changed" constructions
    "{PW_CONTEXT} {PASSWORD} which must be changed {IMMEDIACY}. {VERB} {URL}.",
    "{PW_CONTEXT} {PASSWORD} which must be updated on first login. {VERB} {URL}.",
    "Your account has been reset. {PW_CONTEXT} {PASSWORD} which expires in 24 hours.",

    # "after resetting" phrasing
    "The default password after resetting is {PASSWORD}. {PREFIX}{VERB} {URL}{CLOSING}",
    "After reset, your password is {PASSWORD}. {VERB} {URL} to change it {IMMEDIACY}.",

    # Longer multi-clause patterns
    "{PREFIX}{VERB} {URL} and click on {ACTION}. {PW_CONTEXT} {PASSWORD} and must be updated on first login.",
    "Your account password has been reset to {PASSWORD}. Please {VERB} {URL} and change it {IMMEDIACY}. This is time-sensitive.",

    # Passive/formal voice
    "A temporary password {PASSWORD} has been assigned to your account. {VERB} {URL} to update it.",
    "Your password has been reset to {PASSWORD}. Access the portal at {URL} to set a new one.",

    # Conversational/direct
    "Hi, your new password is {PASSWORD}. Go to {URL} to change it.",
    "FYI your password was reset to {PASSWORD}. Login at {URL} and update it.",
]

# Structural patterns for infrastructure credential templates
INFRASTRUCTURE_CREDENTIAL_PATTERNS = [
    # Simple credential notes
    "{SERVICE} {INFRA_CONTEXT} {USERNAME} {CRED_JOIN} {PASSWORD}",
    "{SERVICE} {INFRA_CONTEXT} {USERNAME} {CRED_JOIN} {PASSWORD}{CLOSING}",
    "{DBTYPE} server {INFRA_CONTEXT} {USERNAME} {CRED_JOIN} {PASSWORD}",
    "{DBTYPE} {INFRA_CONTEXT} {USERNAME} {CRED_JOIN} {PASSWORD}",

    # Hostname-based patterns
    "Server {HOSTNAME}: user {USERNAME}, password {PASSWORD}",
    "Server {HOSTNAME} - {INFRA_CONTEXT} {USERNAME} {CRED_JOIN} {PASSWORD}",
    "{HOSTNAME}: username {USERNAME}, password {PASSWORD}",
    "Host {HOSTNAME} credentials: {USERNAME} / {PASSWORD}",

    # Connection string patterns
    "Connection string: host={HOSTNAME} user={USERNAME} password={PASSWORD}",
    "Connection: {DBTYPE}://{USERNAME}:{PASSWORD}@{HOSTNAME}",
    "DSN: {DBTYPE}://{USERNAME}:{PASSWORD}@{HOSTNAME}/{DBNAME}",
    "{DBTYPE} connection: host={HOSTNAME} port={PORT} user={USERNAME} password={PASSWORD}",

    # Key-value credential patterns
    "{SERVICE} credentials - username: {USERNAME}, password: {PASSWORD}",
    "{SERVICE} credentials: username={USERNAME} password={PASSWORD}",
    "Credentials for {SERVICE}: user {USERNAME}, pass {PASSWORD}",
    "{SERVICE} login: {USERNAME} / {PASSWORD}",
    "Login for {SERVICE} is {USERNAME} with password {PASSWORD}",

    # Short/compact patterns
    "{PW_TERM}: {PASSWORD}. User: {USERNAME}. Service: {SERVICE}",
    "user: {USERNAME}, {PW_TERM}: {PASSWORD}",
    "username: {USERNAME}\npassword: {PASSWORD}",
    "{USERNAME}:{PASSWORD}",
    "{USERNAME} / {PASSWORD}",

    # Descriptive/documentation patterns
    "The {DBTYPE} admin password is {PASSWORD}",
    "The {SERVICE} admin account uses password {PASSWORD}",
    "Default credentials for {SERVICE} are {USERNAME}/{PASSWORD}",
    "Root password for {SERVICE}: {PASSWORD}",
    "{SERVICE} default admin credentials: user={USERNAME}, password={PASSWORD}",
    "Production credentials: {USERNAME} / {PASSWORD} on {HOSTNAME}",

    # Multi-sentence patterns
    "The {SERVICE} is hosted at {HOSTNAME}. Admin credentials: {USERNAME} / {PASSWORD}.",
    "{SERVICE} has been deployed. {INFRA_CONTEXT} {USERNAME} {CRED_JOIN} {PASSWORD}.",
    "Access {SERVICE} at {HOSTNAME}. Username: {USERNAME}. Password: {PASSWORD}.",
    "New {SERVICE} setup complete. Login with {USERNAME} and password {PASSWORD}.",

    # Config/env file style
    "DB_HOST={HOSTNAME}\nDB_USER={USERNAME}\nDB_PASS={PASSWORD}",
    "DATABASE_URL={DBTYPE}://{USERNAME}:{PASSWORD}@{HOSTNAME}",
    "{DBTYPE}_PASSWORD={PASSWORD}",
    "ADMIN_PASSWORD={PASSWORD}",

    # With IP addresses
    "Server at {HOSTNAME}, admin credentials {USERNAME}:{PASSWORD}",
    "{DBTYPE} on {HOSTNAME} - login: {USERNAME}, password: {PASSWORD}",
    "Connect to {HOSTNAME} as {USERNAME} with password {PASSWORD}",

    # Formal/ticket style
    "{PREFIX}the {SERVICE} admin password has been set to {PASSWORD}",
    "{PREFIX}credentials for {SERVICE}: username {USERNAME}, password {PASSWORD}",
    "Ticket #{NUMBER}: {SERVICE} password set to {PASSWORD} for user {USERNAME}",

    # Notification style
    "The {SERVICE} password has been updated to {PASSWORD} for user {USERNAME}.",
    # Urgency
    "{SERVICE} credentials need to be rotated. Current: {USERNAME} / {PASSWORD}.",
    # Conversational
    "FYI the {SERVICE} admin password is {PASSWORD}, user is {USERNAME}.",
    # Passive
    "A new password {PASSWORD} has been assigned for {SERVICE} user {USERNAME}.",
    # Multi-sentence
    "The {SERVICE} at {HOSTNAME} has been provisioned. Login with {USERNAME} and password {PASSWORD}. Change on first access.",
]

# Password context phrases
PW_CONTEXT_PHRASES = [
    "The default password is",
    "Your temporary password is",
    "The initial password is",
    "Your new password is",
    "The reset password is",
    "Use password",
    "Password:",
    "Your password has been set to",
    "The system has assigned",
    "Temporary credential:",
    "Initial access code:",
    "One-time password:",
    "Generated password:",
    "The default password after resetting is",
    "Your temporary password has been set to",
    "The system has reset your password to",
    "Your account password is now",
    "The assigned temporary password is",
    "After reset, your password is",
    "Your temporary access password is",
    "The new temporary password is",
]

CLOUD_AWS_PATTERNS = [
    "AWS {AWS_SERVICE} access key: {ACCESS_KEY}, secret: {SECRET_KEY}",
    "AWS account {ACCOUNT_ID}: access key {ACCESS_KEY}, secret key {SECRET_KEY}",
    "{PREFIX}the AWS {AWS_SERVICE} credentials are access key {ACCESS_KEY} and secret {SECRET_KEY}",
    "IAM user {USERNAME} in account {ACCOUNT_ID}: {ACCESS_KEY} / {SECRET_KEY}",
    "AWS_ACCESS_KEY_ID={ACCESS_KEY}\nAWS_SECRET_ACCESS_KEY={SECRET_KEY}",
    "AWS credentials for {AWS_SERVICE} in {AWS_REGION}: key {ACCESS_KEY}, secret {SECRET_KEY}",
    "Production AWS account ({ACCOUNT_ID}) - {USERNAME}: {ACCESS_KEY} / {SECRET_KEY}",
    "{AWS_SERVICE} ({AWS_REGION}): access key {ACCESS_KEY}{CLOSING}",
    "ARN: arn:aws:iam::{ACCOUNT_ID}:user/{USERNAME}, key: {ACCESS_KEY}",
    "{PREFIX}use access key {ACCESS_KEY} for {AWS_SERVICE} in {AWS_REGION}",
    "AWS console login: account {ACCOUNT_ID}, user {USERNAME}, password {PASSWORD}",
    "[{AWS_REGION}] {AWS_SERVICE} credentials: {ACCESS_KEY} / {SECRET_KEY}",
    "Terraform AWS provider: access_key = \"{ACCESS_KEY}\", secret_key = \"{SECRET_KEY}\", region = \"{AWS_REGION}\"",
    "aws configure --profile prod: key={ACCESS_KEY} secret={SECRET_KEY} region={AWS_REGION}",

    # Notification
    "New AWS credentials have been generated. Access key: {ACCESS_KEY}, secret: {SECRET_KEY}.",
    # Multi-sentence
    "The {AWS_SERVICE} service in {AWS_REGION} is ready. Access key: {ACCESS_KEY}. Secret key: {SECRET_KEY}. Rotate within 90 days.",
    # Conversational
    "Here are the AWS creds for {AWS_SERVICE}: {ACCESS_KEY} / {SECRET_KEY}.",
    # Passive
    "IAM credentials have been issued for account {ACCOUNT_ID}: key {ACCESS_KEY}, secret {SECRET_KEY}.",
    # Formal
    "Please find below the AWS credentials for {AWS_SERVICE}: access key {ACCESS_KEY} and secret key {SECRET_KEY}.",
]

CLOUD_AZURE_PATTERNS = [
    "Azure {AZURE_SERVICE} tenant {TENANT_ID}, client {CLIENT_ID}, secret {CLIENT_SECRET}",
    "AZURE_TENANT_ID={TENANT_ID}\nAZURE_CLIENT_ID={CLIENT_ID}\nAZURE_CLIENT_SECRET={CLIENT_SECRET}",
    "Azure AD app registration: client ID {CLIENT_ID}, secret {CLIENT_SECRET}",
    "{PREFIX}the {AZURE_SERVICE} service principal: tenant {TENANT_ID}, client {CLIENT_ID}, secret {CLIENT_SECRET}",
    "Azure {AZURE_RESOURCE} connection string: {PASSWORD}",
    "SAS token for {AZURE_SERVICE}: {API_KEY}",
    "Azure {AZURE_RESOURCE} admin password: {PASSWORD}",
    "az login --service-principal -u {CLIENT_ID} -p {CLIENT_SECRET} --tenant {TENANT_ID}",
    "Azure Key Vault ({URL}): secret {API_KEY}",
    "Subscription {ACCOUNT_ID}: {AZURE_SERVICE} credentials - client {CLIENT_ID}, secret {CLIENT_SECRET}",
    "Azure SQL connection: Server={HOSTNAME};Database={DBNAME};User={USERNAME};Password={PASSWORD}",
    "{AZURE_SERVICE} managed identity: client ID {CLIENT_ID}{CLOSING}",

    # Notification
    "Azure service principal credentials have been created. Client ID: {CLIENT_ID}, secret: {CLIENT_SECRET}.",
    # Multi-sentence
    "The {AZURE_SERVICE} is configured under tenant {TENANT_ID}. Client ID: {CLIENT_ID}. Client secret: {CLIENT_SECRET}.",
    # Conversational
    "Here are the Azure creds: tenant {TENANT_ID}, client {CLIENT_ID}, secret {CLIENT_SECRET}.",
    # Passive
    "A new client secret {CLIENT_SECRET} has been generated for app {CLIENT_ID}.",
    # Urgency
    "Azure client secret for {CLIENT_ID} expires soon. Current secret: {CLIENT_SECRET}. Rotate immediately.",
]

NETWORK_VPN_PATTERNS = [
    "{VPN_TYPE} gateway: {URL}, username {USERNAME}, password {PASSWORD}",
    "VPN credentials for {VPN_TYPE}: server {URL}, user {USERNAME}, pass {PASSWORD}",
    "{PREFIX}connect to {VPN_TYPE} at {URL} with password {PASSWORD}",
    "WiFi network \"{HOSTNAME}\": security {WIFI_SEC}, password {PASSWORD}",
    "Guest WiFi password: {PASSWORD}. Network: {HOSTNAME}",
    "Corporate WiFi ({HOSTNAME}): {WIFI_SEC}, passphrase {PASSWORD}",
    "{NETWORK_DEVICE} admin console: {URL}, credentials {USERNAME}/{PASSWORD}",
    "Firewall {HOSTNAME} management: user {USERNAME}, password {PASSWORD}",
    "RADIUS shared secret for {HOSTNAME}: {PASSWORD}",
    "{VPN_TYPE} config: remote {URL}, auth {USERNAME}/{PASSWORD}",
    "Network {NETWORK_DEVICE} at {HOSTNAME}: admin password {PASSWORD}{CLOSING}",
    "IPSec pre-shared key: {PASSWORD}. Gateway: {URL}",
    "Site-to-site VPN tunnel: endpoint {URL}, PSK {PASSWORD}",
    "SNMP community string for {HOSTNAME}: {PASSWORD}",

    # Notification
    "VPN access has been configured. Server: {URL}, username: {USERNAME}, password: {PASSWORD}.",
    # Multi-sentence
    "Connect to {VPN_TYPE} at {URL}. Your username is {USERNAME} and password is {PASSWORD}. Change on first login.",
    # Conversational
    "Here are your VPN credentials: server {URL}, user {USERNAME}, pass {PASSWORD}.",
    # Passive
    "A {VPN_TYPE} account has been created for you. Server: {URL}, password: {PASSWORD}.",
    # Urgency
    "{VPN_TYPE} password for {USERNAME} expires soon. Current: {PASSWORD}. Update at {URL}.",
]

CICD_DEVOPS_PATTERNS = [
    "{CICD_PLATFORM} token: {API_KEY}",
    "GitHub personal access token: {API_KEY}",
    "{CICD_PLATFORM} credentials: user {USERNAME}, token {API_KEY}",
    "Docker registry ({REGISTRY}) login: {USERNAME} / {PASSWORD}",
    "{PREFIX}the {CICD_PLATFORM} deploy key is {API_KEY}",
    "DOCKER_USERNAME={USERNAME}\nDOCKER_PASSWORD={PASSWORD}\nDOCKER_REGISTRY={REGISTRY}",
    "{REGISTRY} push credentials: {USERNAME}:{PASSWORD}",
    "Terraform Cloud API token: {API_KEY}",
    "{CICD_PLATFORM} webhook secret: {API_KEY}{CLOSING}",
    "CI/CD pipeline secret ({CICD_PLATFORM}): {API_KEY}",
    "Ansible vault password: {PASSWORD}",
    "Kubernetes service account token: {API_KEY}",
    "Helm chart repo ({URL}): user {USERNAME}, password {PASSWORD}",
    "ArgoCD admin password: {PASSWORD}. Server: {URL}",
    "NPM_TOKEN={API_KEY}",
    "PYPI_TOKEN={API_KEY}",
    "{CICD_PLATFORM} SSH deploy key for {URL}: {SSH_KEY}",

    # Notification
    "A new {CICD_PLATFORM} token has been generated: {API_KEY}.",
    # Multi-sentence
    "The {CICD_PLATFORM} pipeline is configured. Deploy token: {API_KEY}. Registry: {REGISTRY}, user: {USERNAME}, password: {PASSWORD}.",
    # Conversational
    "Here's the {CICD_PLATFORM} deploy key: {API_KEY}.",
    # Passive
    "A deploy token {API_KEY} has been created for the {CICD_PLATFORM} pipeline.",
    # Urgency
    "{CICD_PLATFORM} token {API_KEY} needs rotation. Current credentials: {USERNAME} / {PASSWORD}.",
]

EMAIL_SMTP_PATTERNS = [
    "SMTP server: {SMTP_SVR}, port {PORT}, user {EMAIL}, password {PASSWORD}",
    "Email credentials: {SMTP_SVR}:{PORT}, login {EMAIL}/{PASSWORD}",
    "SMTP_HOST={SMTP_SVR}\nSMTP_PORT={PORT}\nSMTP_USER={EMAIL}\nSMTP_PASS={PASSWORD}",
    "{PREFIX}the outgoing mail server is {SMTP_SVR} with password {PASSWORD}",
    "Mail relay: {SMTP_SVR}, auth {EMAIL} / {PASSWORD}",
    "{EMAIL_PROTO} server {SMTP_SVR}: username {EMAIL}, password {PASSWORD}",
    "Office 365 SMTP: smtp.office365.com:587, user {EMAIL}, pass {PASSWORD}",
    "SendGrid API key for transactional email: {API_KEY}",
    "Mailgun API key: {API_KEY}, domain: {DOMAIN}",
    "Email service ({SMTP_SVR}): app password {PASSWORD}{CLOSING}",
    "IMAP login: server {SMTP_SVR}, user {EMAIL}, password {PASSWORD}",
    "Exchange server: {URL}, mailbox {EMAIL}, password {PASSWORD}",

    # Notification
    "SMTP credentials have been configured. Server: {SMTP_SVR}, user: {EMAIL}, password: {PASSWORD}.",
    # Multi-sentence
    "The mail server is {SMTP_SVR} on port {PORT}. Login with {EMAIL} and password {PASSWORD}.",
    # Conversational
    "SMTP details: server {SMTP_SVR}, port {PORT}, user {EMAIL}, pass {PASSWORD}.",
    # Passive
    "An SMTP account has been provisioned. Server: {SMTP_SVR}, credentials: {EMAIL} / {PASSWORD}.",
    # Formal
    "Please configure your email client with server {SMTP_SVR}, port {PORT}, username {EMAIL}, and password {PASSWORD}.",
]

FINANCIAL_BANKING_PATTERNS = [
    "{TRANSACTION} of {AMOUNT} to account {ACCOUNT} at {BANK}",
    "Wire transfer: {AMOUNT} to {BANK}, account {ACCOUNT}, routing {ROUTING}",
    "ACH details: routing {ROUTING}, account {ACCOUNT}, amount {AMOUNT}",
    "Payment to {NAME}: {AMOUNT} via {TRANSACTION} to {BANK} account {ACCOUNT}",
    "Bank: {BANK}, Account: {ACCOUNT}, Routing: {ROUTING}",
    "{PREFIX}{TRANSACTION} of {AMOUNT} to {NAME} at {BANK}{CLOSING}",
    "Invoice #{NUMBER}: {AMOUNT} payable to account {ACCOUNT} at {BANK}",
    "Direct deposit: {BANK} routing {ROUTING} account {ACCOUNT}",
    "SWIFT code: {ROUTING}. Beneficiary account: {ACCOUNT}. Amount: {AMOUNT}",
    "Payroll: {NAME} - {BANK} account {ACCOUNT}, {AMOUNT} per period",
    "Treasury {TRANSACTION}: {AMOUNT} from account {ACCOUNT} to {NAME}",
    "Credit facility: {AMOUNT} at {RATE}% from {BANK}. Account: {ACCOUNT}",
    "Company bank details: {BANK}, routing {ROUTING}, account {ACCOUNT}",

    # Multi-sentence
    "Wire transfer authorized. Amount: {AMOUNT}. Destination: {BANK}, account {ACCOUNT}, routing {ROUTING}.",
    # Notification
    "A payment of {AMOUNT} has been initiated to {BANK} account {ACCOUNT}.",
    # Passive
    "Funds of {AMOUNT} have been wired to routing {ROUTING}, account {ACCOUNT} at {BANK}.",
    # Formal
    "Please process a transfer of {AMOUNT} to {BANK}. Routing: {ROUTING}. Account: {ACCOUNT}.",
    # Conversational
    "FYI wired {AMOUNT} to {BANK}, acct {ACCOUNT}, routing {ROUTING}.",
]

LEGAL_CONFIDENTIAL_PATTERNS = [
    "{LEGAL_TYPE} between {COMPANY} and {LEGAL_PARTY}: {AMOUNT}",
    "Settlement: {AMOUNT} to {LEGAL_PARTY}. Case #{NUMBER}. Confidential.",
    "{LEGAL_TYPE} signed {DATE}: {COMPANY} agrees to pay {AMOUNT}",
    "Acquisition of {COMPANY} for {AMOUNT}. Closing date: {DATE}",
    "M&A: {COMPANY} valued at {AMOUNT}. {LEGAL_PARTY} advising.",
    "{PREFIX}{LEGAL_TYPE} with {COMPANY}: total value {AMOUNT}{CLOSING}",
    "Confidential: {COMPANY} settlement for {AMOUNT} on {DATE}",
    "Board approved: acquire {COMPANY} at {AMOUNT} per share",
    "Termination agreement: {NAME} receives {AMOUNT}. Effective {DATE}.",
    "Non-compete: {NAME}, {COMPANY}, {DATE} through {DATE}. Penalty: {AMOUNT}",
    "{LEGAL_TYPE}: {COMPANY}. Effective {DATE}. Governing law: Delaware.",
    "Pending litigation: {COMPANY} vs {LEGAL_PARTY}. Reserve: {AMOUNT}",
    "Due diligence: {COMPANY} EBITDA {AMOUNT}. LOI signed {DATE}.",

    # Notification
    "Settlement approved: {AMOUNT} to {LEGAL_PARTY}. {LEGAL_TYPE} signed {DATE}.",
    # Multi-sentence
    "The {LEGAL_TYPE} with {COMPANY} has been finalized. Settlement amount: {AMOUNT}. Effective: {DATE}. This is strictly confidential.",
    # Passive
    "A {LEGAL_TYPE} has been executed between the parties. {COMPANY} to receive {AMOUNT}.",
    # Conversational
    "FYI the {COMPANY} deal closed at {AMOUNT}. {LEGAL_TYPE} signed {DATE}.",
    # Urgency
    "Confidential: {LEGAL_TYPE} for {COMPANY} at {AMOUNT} requires signature by {DATE}.",
]

MEDICAL_HIPAA_PATTERNS = [
    "Patient {NAME}, MRN {MRN}: {DIAGNOSIS_CODE}. Attending: Dr. {NAME}",
    "Medical record: {NAME}, DOB {DATE}, MRN {MRN}",
    "{FACILITY} - patient {NAME}: {DIAGNOSIS_CODE}, admitted {DATE}",
    "Prescription for {NAME} (MRN {MRN}): {MEDICATION} {DOSAGE}. Dr. {NAME}",
    "Lab results for {NAME} ({MRN}): {CODE}. {DEPARTMENT} department.",
    "Discharge summary: {NAME}, MRN {MRN}. Admitted {DATE}. {DIAGNOSIS_CODE}",
    "HIPAA: patient {NAME}, SSN ending {SSN_LAST4}, MRN {MRN}",
    "Insurance: {NAME}, member ID {MRN}, group #{NUMBER}",
    "{DEPARTMENT}: {NAME}, {DIAGNOSIS_CODE}. Follow-up {DATE}",
    "Surgical report: {NAME}, MRN {MRN}. Procedure: {CODE}. Date: {DATE}",
    "Mental health record: {NAME}. Provider: {FACILITY}. Session {DATE}",
    "Radiology: {NAME}, MRN {MRN}. Findings: {CODE}. Ordered by Dr. {NAME}",

    # Notification
    "Lab results are available for patient {NAME}, MRN {MRN}. {DIAGNOSIS_CODE}.",
    # Multi-sentence
    "Patient {NAME} (MRN: {MRN}) was admitted on {DATE}. Diagnosis: {DIAGNOSIS_CODE}. Attending physician notified.",
    # Passive
    "Results for {NAME} (MRN {MRN}) have been posted. {DIAGNOSIS_CODE}.",
    # Formal
    "This is to notify that patient {NAME}, MRN {MRN}, has been diagnosed with {DIAGNOSIS_CODE} on {DATE}.",
    # Conversational
    "FYI patient {NAME} MRN {MRN} labs came back: {DIAGNOSIS_CODE}.",
]

CUSTOMER_PII_PATTERNS = [
    "Customer: {NAME}, SSN: {SSN}, DOB: {DATE}",
    "{PII_DOC}: {NAME}, card ending {CARD_LAST4}, exp {DATE}",
    "Account holder: {NAME}. Address: {ADDRESS}. Phone: {PHONE}. Email: {EMAIL}",
    "Member profile: {NAME}, ID {EMPLOYEE_ID}, email {EMAIL}, phone {PHONE}",
    "Credit card: {NAME}, ending {CARD_LAST4}, billing {ADDRESS}",
    "Customer {NAME}: SSN {SSN}, DL #{NUMBER}",
    "KYC: {NAME}, DOB {DATE}, SSN {SSN}, address {ADDRESS}",
    "Loyalty account: {NAME}, email {EMAIL}. Points: {AMOUNT}. Phone: {PHONE}",
    "Subscriber: {NAME}, phone {PHONE}, address {ADDRESS}, since {DATE}",
    "Dispute: {NAME}, card ending {CARD_LAST4}, amount {AMOUNT}, date {DATE}",
    "Identity verification: {NAME}, SSN ending {SSN_LAST4}, DOB {DATE}",
    "Data export: {NAME}, {EMAIL}, {PHONE}, {ADDRESS}, account since {DATE}",

    # Notification
    "New customer registered: {NAME}, SSN: {SSN}, DOB: {DATE}.",
    # Multi-sentence
    "Customer {NAME} has been verified. SSN: {SSN}. Date of birth: {DATE}. Address: {ADDRESS}.",
    # Passive
    "Account for {NAME} has been created. SSN ending {SSN_LAST4} verified.",
    # Formal
    "KYC verification complete for {NAME}. SSN: {SSN}, DOB: {DATE}, address: {ADDRESS}.",
    # Conversational
    "New account: {NAME}, DOB {DATE}, SSN {SSN}. Address: {ADDRESS}.",
]

INTERNAL_STRATEGY_PATTERNS = [
    "{MEETING}: {STRATEGY_ACTION} acquisition of {COMPANY} for {AMOUNT}",
    "Confidential: {COMPANY} Q{QUARTER} revenue {AMOUNT}. Not yet public.",
    "{MEETING} minutes: {NAME} {STRATEGY_ACTION} {AMOUNT} budget for {DEPARTMENT}",
    "Pre-announcement: {COMPANY} to lay off {NUMBER} employees effective {DATE}",
    "M&A pipeline: {COMPANY} target, valuation {AMOUNT}, LOI by {DATE}",
    "Strategic initiative: invest {AMOUNT} in {DEPARTMENT}. Sponsor: {NAME}",
    "{PREFIX}board {STRATEGY_ACTION} {AMOUNT} share buyback program{CLOSING}",
    "Earnings preview: Q{QUARTER} EPS {AMOUNT}. Embargo until {DATE}.",
    "Restructuring: {DEPARTMENT} headcount reduced by {NUMBER}. Savings: {AMOUNT}",
    "{MEETING}: CEO {NAME} proposed merger with {COMPANY}. Valued at {AMOUNT}.",
    "Insider information: {COMPANY} patent settlement {AMOUNT}. Announce {DATE}.",
    "Compensation committee: CEO {NAME} total comp {AMOUNT} for FY{YEAR}",

    # Notification
    "Board has approved acquisition of {COMPANY} for {AMOUNT}. Closing: {DATE}.",
    # Multi-sentence
    "{MEETING} update: {STRATEGY_ACTION} {COMPANY} acquisition at {AMOUNT}. Target close date: {DATE}. Strictly confidential.",
    # Passive
    "The acquisition of {COMPANY} has been {STRATEGY_ACTION} at a valuation of {AMOUNT}.",
    # Formal
    "This is to confirm that the {MEETING} has {STRATEGY_ACTION} the {COMPANY} transaction for {AMOUNT}.",
    # Conversational
    "FYI board {STRATEGY_ACTION} the {COMPANY} deal at {AMOUNT}. Closing {DATE}.",
]

CERTIFICATE_TLS_PATTERNS = [
    "{CERT_TYPE} certificate for {DOMAIN}: private key passphrase {PASSWORD}",
    "SSL cert ({DOMAIN}): key file /etc/ssl/{DOMAIN}.key, passphrase {PASSWORD}",
    "{CERT_TYPE} ({CERT_FORMAT}): {DOMAIN}, expires {DATE}, passphrase {PASSWORD}",
    "Wildcard cert *.{DOMAIN}: PKCS12 password {PASSWORD}",
    "Certificate Authority: {URL}. Signing key passphrase: {PASSWORD}",
    "{PREFIX}the {CERT_TYPE} private key password for {DOMAIN} is {PASSWORD}",
    "JKS keystore: /opt/certs/{DOMAIN}.jks, password {PASSWORD}",
    "Let's Encrypt cert for {DOMAIN}: account key {API_KEY}",
    "Code signing certificate: {DOMAIN}, key password {PASSWORD}, expires {DATE}",
    "Client certificate for {USERNAME}@{DOMAIN}: passphrase {PASSWORD}",
    "PFX export password for {DOMAIN}: {PASSWORD}",
    "Root CA key passphrase: {PASSWORD}. Cert path: /etc/pki/ca/{DOMAIN}.crt",

    # Notification
    "SSL certificate for {DOMAIN} has been renewed. Key passphrase: {PASSWORD}.",
    # Multi-sentence
    "The {CERT_TYPE} certificate for {DOMAIN} expires on {DATE}. Keystore password: {PASSWORD}. Please renew before expiration.",
    # Passive
    "A new {CERT_TYPE} certificate has been issued for {DOMAIN}. Passphrase: {PASSWORD}.",
    # Formal
    "Please find the {CERT_TYPE} certificate details: domain {DOMAIN}, format {CERT_FORMAT}, passphrase {PASSWORD}.",
    # Urgency
    "Certificate for {DOMAIN} expires {DATE}. Current key passphrase: {PASSWORD}. Renew immediately.",
]

ENCRYPTION_KEYS_PATTERNS = [
    "HashiCorp Vault token: {API_KEY}. URL: {URL}",
    "Vault ({URL}): root token {API_KEY}, unseal key {PASSWORD}",
    "KMS key ID: {API_KEY}. Region: {AWS_REGION}",
    "{ENCRYPTION_TYPE} master key: {PASSWORD}",
    "VAULT_TOKEN={API_KEY}\nVAULT_ADDR={URL}",
    "GPG passphrase for {EMAIL}: {PASSWORD}",
    "{PREFIX}the {ENCRYPTION_TYPE} encryption key is {PASSWORD}",
    "Secrets path: {VAULT_PATH}. Token: {API_KEY}",
    "SOPS key: {API_KEY}. Config: .sops.yaml",
    "Age recipient key: {API_KEY}",
    "LUKS passphrase for /dev/sda2: {PASSWORD}",
    "Sealed secrets key: {API_KEY}. Namespace: {HOSTNAME}",
    "Backup encryption passphrase: {PASSWORD}. Algorithm: {ENCRYPTION_TYPE}",

    # Notification
    "New Vault token has been generated: {API_KEY}. Endpoint: {URL}.",
    # Multi-sentence
    "The secrets vault at {URL} is ready. Root token: {API_KEY}. Unseal key: {PASSWORD}. Store securely.",
    # Passive
    "A {ENCRYPTION_TYPE} key has been provisioned. Key ID: {API_KEY}.",
    # Formal
    "Please configure the vault at {URL} using token {API_KEY} and unseal key {PASSWORD}.",
    # Conversational
    "Vault is up at {URL}. Token: {API_KEY}, unseal: {PASSWORD}.",
]

OAUTH_SSO_PATTERNS = [
    "{OAUTH_PROVIDER} client ID: {CLIENT_ID}, secret: {CLIENT_SECRET}",
    "OAuth2 ({OAUTH_PROVIDER}): client_id={CLIENT_ID}, client_secret={CLIENT_SECRET}",
    "SSO config ({OAUTH_PROVIDER}): tenant {TENANT_ID}, client {CLIENT_ID}, secret {CLIENT_SECRET}",
    "SAML IdP ({OAUTH_PROVIDER}): metadata URL {URL}, signing cert password {PASSWORD}",
    "OIDC discovery: {URL}/.well-known/openid-configuration. Client secret: {CLIENT_SECRET}",
    "{PREFIX}{OAUTH_PROVIDER} app credentials: client {CLIENT_ID}, secret {CLIENT_SECRET}",
    "Redirect URI: {URL}/callback. Client secret: {CLIENT_SECRET}",
    "{OAUTH_PROVIDER} API: client_credentials grant, secret {CLIENT_SECRET}",
    "JWT signing key ({OAUTH_PROVIDER}): {API_KEY}",
    "SSO admin ({OAUTH_PROVIDER}): {URL}, API token {API_KEY}",
    "SCIM provisioning token ({OAUTH_PROVIDER}): {API_KEY}",
    "MFA bypass code ({OAUTH_PROVIDER}): {PASSWORD}",

    # Notification
    "OAuth app registered with {OAUTH_PROVIDER}. Client ID: {CLIENT_ID}, secret: {CLIENT_SECRET}.",
    # Multi-sentence
    "SSO has been configured with {OAUTH_PROVIDER}. Client ID: {CLIENT_ID}. Client secret: {CLIENT_SECRET}. Discovery URL: {URL}.",
    # Passive
    "A new client secret {CLIENT_SECRET} has been generated for {OAUTH_PROVIDER} app {CLIENT_ID}.",
    # Formal
    "Please update the {OAUTH_PROVIDER} configuration with client ID {CLIENT_ID} and secret {CLIENT_SECRET}.",
    # Urgency
    "{OAUTH_PROVIDER} client secret for {CLIENT_ID} expires soon. Current: {CLIENT_SECRET}. Rotate immediately.",
]

DATABASE_CONNECTION_PATTERNS = [
    "jdbc:{DBTYPE}://{HOSTNAME}:{PORT}/{DBNAME}?user={USERNAME}&password={PASSWORD}",
    "{DBTYPE}://{USERNAME}:{PASSWORD}@{HOSTNAME}:{PORT}/{DBNAME}",
    "DSN: {DBTYPE}://{USERNAME}:{PASSWORD}@{HOSTNAME}/{DBNAME}",
    "Database: {DBTYPE} on {HOSTNAME}:{PORT}. DB: {DBNAME}. User: {USERNAME}. Pass: {PASSWORD}",
    "DATABASE_URL={DBTYPE}://{USERNAME}:{PASSWORD}@{HOSTNAME}:{PORT}/{DBNAME}",
    "Connection: host={HOSTNAME} port={PORT} dbname={DBNAME} user={USERNAME} password={PASSWORD}",
    "{DBTYPE} connection string: Server={HOSTNAME},{PORT};Database={DBNAME};User Id={USERNAME};Password={PASSWORD}",
    "Data Source={HOSTNAME};Initial Catalog={DBNAME};User ID={USERNAME};Password={PASSWORD}",
    "ODBC: Driver={DBTYPE};Server={HOSTNAME};Port={PORT};Database={DBNAME};Uid={USERNAME};Pwd={PASSWORD}",
    "{PREFIX}{DBTYPE} production database: {HOSTNAME}:{PORT}/{DBNAME}, user {USERNAME}, password {PASSWORD}",
    "Read replica: {HOSTNAME}:{PORT}, db {DBNAME}, credentials {USERNAME}/{PASSWORD}",
    "Connection pooler: pgbouncer://{USERNAME}:{PASSWORD}@{HOSTNAME}:{PORT}/{DBNAME}",

    # Notification
    "Database credentials have been updated. Host: {HOSTNAME}, user: {USERNAME}, password: {PASSWORD}.",
    # Multi-sentence
    "The {DBTYPE} database is available at {HOSTNAME}:{PORT}. Database name: {DBNAME}. Login with {USERNAME} and password {PASSWORD}.",
    # Passive
    "A {DBTYPE} account has been created. Host: {HOSTNAME}, database: {DBNAME}, user: {USERNAME}, password: {PASSWORD}.",
    # Conversational
    "DB creds: {DBTYPE} on {HOSTNAME}:{PORT}/{DBNAME}, user {USERNAME}, pass {PASSWORD}.",
    # Formal
    "Please connect to {DBTYPE} at {HOSTNAME}:{PORT} using database {DBNAME}, username {USERNAME}, and password {PASSWORD}.",
]

VENDOR_PARTNER_PATTERNS = [
    "{VENDOR} API key: {API_KEY}. Endpoint: {URL}",
    "Vendor ({VENDOR}) credentials: user {USERNAME}, key {API_KEY}",
    "Partner portal ({VENDOR}): {URL}, login {USERNAME}/{PASSWORD}",
    "{VENDOR} integration: API URL {URL}, token {API_KEY}",
    "{PREFIX}{VENDOR} access credentials: API key {API_KEY}{CLOSING}",
    "Third-party service ({VENDOR}): endpoint {URL}, secret {PASSWORD}",
    "{VENDOR} webhook URL: {URL}, signing secret {API_KEY}",
    "Vendor SFTP ({VENDOR}): host {HOSTNAME}, user {USERNAME}, password {PASSWORD}",
    "Partner API ({VENDOR}): client ID {CLIENT_ID}, secret {CLIENT_SECRET}",
    "{VENDOR} sandbox: {URL}, test key {API_KEY}",
    "{VENDOR} production key: {API_KEY}. Rate limit: 1000/min.",
    "SLA with {VENDOR}: support portal {URL}, admin password {PASSWORD}",

    # Notification
    "{VENDOR} integration is live. API key: {API_KEY}. Endpoint: {URL}.",
    # Multi-sentence
    "The {VENDOR} API has been configured. Endpoint: {URL}. API key: {API_KEY}. Contact vendor for support.",
    # Passive
    "Access to {VENDOR} has been provisioned. Portal: {URL}, credentials: {USERNAME} / {PASSWORD}.",
    # Formal
    "Please configure the {VENDOR} integration with endpoint {URL} and API key {API_KEY}.",
    # Conversational
    "Here's the {VENDOR} API key: {API_KEY}. Endpoint: {URL}.",
]

SAAS_CREDENTIALS_PATTERNS = [
    "{SAAS_PLATFORM} login: {USERNAME} / {PASSWORD}",
    "{SAAS_PLATFORM} admin account: {EMAIL}, password {PASSWORD}",
    "{SAAS_PLATFORM} API token: {API_KEY}",
    "{SAAS_PLATFORM} ({URL}): user {USERNAME}, password {PASSWORD}",
    "{PREFIX}the {SAAS_PLATFORM} service account password is {PASSWORD}",
    "{SAAS_PLATFORM} integration token: {API_KEY}. Workspace: {HOSTNAME}",
    "SAAS_TOKEN={API_KEY}\nSAAS_URL={URL}",
    "{SAAS_PLATFORM} OAuth app: client ID {CLIENT_ID}, secret {CLIENT_SECRET}",
    "{SAAS_PLATFORM} SSO admin: {URL}, API key {API_KEY}",
    "{SAAS_PLATFORM} bot token: {API_KEY}",
    "Service account for {SAAS_PLATFORM}: {EMAIL} / {PASSWORD}",
    "{SAAS_PLATFORM} webhook secret: {API_KEY}. Endpoint: {URL}",

    # Notification
    "Your {SAAS_PLATFORM} account has been created. Login: {USERNAME}, password: {PASSWORD}.",
    # Multi-sentence
    "{SAAS_PLATFORM} is ready. Log in at the portal with username {USERNAME} and password {PASSWORD}. Change on first login.",
    # Passive
    "A {SAAS_PLATFORM} account has been provisioned. Credentials: {EMAIL} / {PASSWORD}.",
    # Formal
    "Please sign in to {SAAS_PLATFORM} using username {USERNAME} and password {PASSWORD}.",
    # Urgency
    "{SAAS_PLATFORM} password for {USERNAME} expires soon. Current: {PASSWORD}. Update immediately.",
]


# ============================================================================
# DOMAIN CONFIGURATIONS
# ============================================================================

DOMAIN_CONFIGS = {
    "it_password": {
        "name": "IT/Password Reset",
        "slot_types": ["PASSWORD", "URL", "API_KEY", "USERNAME", "EMAIL"],
        "primary_slot": "PASSWORD",
        "patterns": PASSWORD_RESET_PATTERNS,
        "base_templates": [
            "Please navigate to {URL} and click on Need help signing in. The default password after resetting is {PASSWORD} which must be changed immediately.",
            "Visit {URL} to reset your password. Your temporary credential is {PASSWORD} and must be updated on first login.",
            "Access the login portal at {URL} and select forgot password. The system will assign {PASSWORD} as your temporary access code.",
            "For password recovery, go to {URL} and follow the reset process. Default credentials are {PASSWORD}.",
            "The SSO portal at {URL} requires password reset. Use {PASSWORD} for initial access then change immediately.",
            "Your account password has been reset. New temporary password: {PASSWORD}. Change at {URL}.",
            "Password reset complete for your account. Temporary access: {PASSWORD}. Login at {URL} to update.",
        ]
    },
    "hr_employee": {
        "name": "HR/Employee Records",
        "slot_types": ["NAME", "SALARY", "SSN", "EMPLOYEE_ID", "DATE", "EMAIL"],
        "primary_slot": "NAME",
        "patterns": [
            "Employee {NAME} salary adjusted to {SALARY} effective {DATE}.",
            "{NAME} ({EMPLOYEE_ID}) - Salary: {SALARY}",
            "Personnel record: {NAME}, ID {EMPLOYEE_ID}, compensation {SALARY}.",
            "New hire {NAME} starting {DATE} at {SALARY} annually.",
            "{NAME_PREFIX}{NAME} {SALARY_ACTION} to {SALARY} {DATE_CTX} {DATE}.",

            # Multi-sentence
            "{NAME} has been hired starting {DATE}. Annual compensation: {SALARY}. Please update payroll.",
            # Notification
            "Salary adjustment notification: {NAME} adjusted to {SALARY} effective {DATE}.",
            # Passive
            "{NAME}'s compensation has been updated to {SALARY} as of {DATE}.",
            # Formal
            "This is to confirm that {NAME} (ID: {EMPLOYEE_ID}) salary is now {SALARY}.",
            # Conversational
            "FYI {NAME} is starting at {SALARY} on {DATE}.",
            # With context
            "HR update: {NAME}, employee ID {EMPLOYEE_ID}, annual salary {SALARY}, start date {DATE}.",
        ],
        "base_templates": [
            "Employee {NAME} salary adjusted to {SALARY} annually effective {DATE}.",
            "Compensation package for {NAME} includes base salary {SALARY}.",
            "New hire {NAME} starting {DATE} with salary {SALARY}.",
            "{NAME} has been onboarded. Employee ID: {EMPLOYEE_ID}. Annual salary: {SALARY}. Start date: {DATE}. Please update payroll records.",
            "HR notification: {NAME} (ID: {EMPLOYEE_ID}) compensation updated to {SALARY} effective {DATE}.",
            "This is to confirm that {NAME} will join the team on {DATE} with an annual salary of {SALARY}.",
            "FYI {NAME} salary is now {SALARY} as of {DATE}. Employee ID: {EMPLOYEE_ID}.",
        ]
    },
    "api_developer": {
        "name": "API/Developer",
        "slot_types": ["API_KEY", "URL", "TOKEN", "SECRET"],
        "primary_slot": "API_KEY",
        "patterns": [
            "API endpoint: {URL}, Key: {API_KEY}.",
            "Bearer token for {URL}: {API_KEY}.",
            "curl -H 'Authorization: Bearer {API_KEY}' {URL}",
            "Service URL: {URL} with auth {API_KEY}.",

            # Multi-sentence
            "The API is available at {URL}. Use key {API_KEY} for authentication.",
            # Notification
            "Your API key has been generated: {API_KEY}. Endpoint: {URL}.",
            # Passive
            "An API key {API_KEY} has been provisioned for endpoint {URL}.",
            # Conversational
            "Here's your API key: {API_KEY}. The endpoint is {URL}.",
            # Urgency
            "API key {API_KEY} for {URL} expires in 30 days. Rotate immediately.",
        ],
        "base_templates": [
            "API endpoint: {URL}, Key: {API_KEY}.",
            "Authentication token: {API_KEY}. Endpoint: {URL}.",
            "Production endpoint {URL} requires key {API_KEY}.",
            "Your API key has been generated: {API_KEY}. Use it to authenticate at {URL}. Rotate within 90 days.",
            "The API at {URL} is ready. Your key is {API_KEY}. Include it in the Authorization header.",
            "Here is your API key: {API_KEY}. The endpoint is {URL}. Please store it securely.",
        ]
    },
    "infrastructure_credentials": {
        "name": "Infrastructure/Server Credentials",
        "slot_types": ["PASSWORD", "USERNAME", "HOSTNAME", "DBNAME", "PORT"],
        "primary_slot": "PASSWORD",
        "patterns": INFRASTRUCTURE_CREDENTIAL_PATTERNS,
        "base_templates": [
            "Production database server admin username is {USERNAME} with password {PASSWORD}",
            "Database server admin username is {USERNAME} with password {PASSWORD}",
            "Server admin username is {USERNAME} with password {PASSWORD}",
            "Production database server admin username is admin with password {PASSWORD}",
            "The admin username is {USERNAME} and the password is {PASSWORD}",
            "{USERNAME}:{PASSWORD}",
            "Default credentials: {USERNAME} / {PASSWORD}",
            "Login: {USERNAME}, password: {PASSWORD}",
            "Server credentials - user: {USERNAME}, pass: {PASSWORD}",
            "Admin password: {PASSWORD}",
            "Root password for the database server is {PASSWORD}",
        ]
    },
    "cloud_aws": {
        "name": "Cloud/AWS Credentials",
        "slot_types": ["ACCESS_KEY", "SECRET_KEY", "ACCOUNT_ID", "PASSWORD", "USERNAME"],
        "primary_slot": "ACCESS_KEY",
        "patterns": CLOUD_AWS_PATTERNS,
        "base_templates": [
            "AWS account {ACCOUNT_ID}: access key {ACCESS_KEY}, secret key {SECRET_KEY}",
            "IAM user credentials: access key {ACCESS_KEY}, secret {SECRET_KEY}",
            "AWS_ACCESS_KEY_ID={ACCESS_KEY}\nAWS_SECRET_ACCESS_KEY={SECRET_KEY}",
            "AWS console login: account {ACCOUNT_ID}, user {USERNAME}, password {PASSWORD}",
            "Production AWS credentials: {ACCESS_KEY} / {SECRET_KEY}",
        ]
    },
    "cloud_azure": {
        "name": "Cloud/Azure Credentials",
        "slot_types": ["CLIENT_ID", "CLIENT_SECRET", "TENANT_ID", "PASSWORD", "ACCOUNT_ID"],
        "primary_slot": "CLIENT_SECRET",
        "patterns": CLOUD_AZURE_PATTERNS,
        "base_templates": [
            "Azure AD: tenant {TENANT_ID}, client {CLIENT_ID}, secret {CLIENT_SECRET}",
            "AZURE_TENANT_ID={TENANT_ID}\nAZURE_CLIENT_ID={CLIENT_ID}\nAZURE_CLIENT_SECRET={CLIENT_SECRET}",
            "Azure service principal: client {CLIENT_ID}, secret {CLIENT_SECRET}",
            "Azure SQL connection: Server={HOSTNAME};User={USERNAME};Password={PASSWORD}",
        ]
    },
    "network_vpn": {
        "name": "Network/VPN Credentials",
        "slot_types": ["PASSWORD", "USERNAME", "URL", "HOSTNAME"],
        "primary_slot": "PASSWORD",
        "patterns": NETWORK_VPN_PATTERNS,
        "base_templates": [
            "VPN gateway: {URL}, username {USERNAME}, password {PASSWORD}",
            "Corporate WiFi password: {PASSWORD}",
            "Firewall admin console: {URL}, credentials {USERNAME}/{PASSWORD}",
            "IPSec pre-shared key: {PASSWORD}",
            "Guest WiFi password: {PASSWORD}. Network: {HOSTNAME}",
        ]
    },
    "ci_cd_devops": {
        "name": "CI/CD DevOps Secrets",
        "slot_types": ["API_KEY", "PASSWORD", "USERNAME", "URL", "SSH_KEY"],
        "primary_slot": "API_KEY",
        "patterns": CICD_DEVOPS_PATTERNS,
        "base_templates": [
            "GitHub personal access token: {API_KEY}",
            "Docker registry login: {USERNAME} / {PASSWORD}",
            "Jenkins admin password: {PASSWORD}",
            "Terraform Cloud API token: {API_KEY}",
            "Ansible vault password: {PASSWORD}",
            "NPM_TOKEN={API_KEY}",
        ]
    },
    "email_smtp": {
        "name": "Email/SMTP Credentials",
        "slot_types": ["PASSWORD", "EMAIL", "URL", "API_KEY"],
        "primary_slot": "PASSWORD",
        "patterns": EMAIL_SMTP_PATTERNS,
        "base_templates": [
            "SMTP server: smtp.company.com, port 587, user {EMAIL}, password {PASSWORD}",
            "SendGrid API key: {API_KEY}",
            "Office 365 SMTP: user {EMAIL}, password {PASSWORD}",
            "SMTP_HOST=smtp.company.com\nSMTP_USER={EMAIL}\nSMTP_PASS={PASSWORD}",
        ]
    },
    "financial_banking": {
        "name": "Financial/Banking Details",
        "slot_types": ["ACCOUNT", "AMOUNT", "ROUTING", "NAME"],
        "primary_slot": "ACCOUNT",
        "patterns": FINANCIAL_BANKING_PATTERNS,
        "base_templates": [
            "Wire transfer: {AMOUNT} to account {ACCOUNT}, routing {ROUTING}",
            "Bank account: {ACCOUNT}, routing: {ROUTING}",
            "Payment to {NAME}: {AMOUNT} to account {ACCOUNT}",
            "Direct deposit: routing {ROUTING}, account {ACCOUNT}",
            "SWIFT transfer: {AMOUNT} to account {ACCOUNT}",
        ]
    },
    "legal_confidential": {
        "name": "Legal/Confidential",
        "slot_types": ["AMOUNT", "COMPANY", "NAME", "DATE"],
        "primary_slot": "AMOUNT",
        "patterns": LEGAL_CONFIDENTIAL_PATTERNS,
        "base_templates": [
            "Settlement: {AMOUNT} to {COMPANY}. Confidential.",
            "Acquisition of {COMPANY} for {AMOUNT}. Closing: {DATE}",
            "NDA between {COMPANY} and {NAME}. Signed {DATE}.",
            "Board approved acquisition: {COMPANY} at {AMOUNT}",
            "The settlement agreement with {COMPANY} has been finalized at {AMOUNT}. Effective {DATE}. This is strictly confidential.",
            "Confidential: {COMPANY} deal closed at {AMOUNT}. NDA signed {DATE}. Do not distribute.",
            "This is to confirm the merger with {COMPANY} for {AMOUNT}. Closing date: {DATE}. Board approval received.",
        ]
    },
    "medical_hipaa": {
        "name": "Medical/HIPAA Records",
        "slot_types": ["NAME", "MRN", "DATE", "CODE", "SSN_LAST4"],
        "primary_slot": "NAME",
        "patterns": MEDICAL_HIPAA_PATTERNS,
        "base_templates": [
            "Patient {NAME}, MRN {MRN}: diagnosis {CODE}",
            "Medical record: {NAME}, DOB {DATE}, MRN {MRN}",
            "Prescription for {NAME} (MRN {MRN}): medication, Dr. {NAME}",
            "HIPAA: patient {NAME}, SSN ending {SSN_LAST4}, MRN {MRN}",
            "Patient {NAME} (MRN: {MRN}) was admitted on {DATE}. Diagnosis: {CODE}. Attending physician has been notified.",
            "Lab results for patient {NAME}, MRN {MRN}, are now available. Diagnosis code: {CODE}.",
            "This is to notify that patient {NAME}, MRN {MRN}, has been diagnosed with {CODE} on {DATE}.",
        ]
    },
    "customer_pii": {
        "name": "Customer PII",
        "slot_types": ["NAME", "SSN", "EMAIL", "PHONE", "ADDRESS", "DATE"],
        "primary_slot": "NAME",
        "patterns": CUSTOMER_PII_PATTERNS,
        "base_templates": [
            "Customer: {NAME}, SSN: {SSN}, DOB: {DATE}",
            "Account holder: {NAME}. Email: {EMAIL}. Phone: {PHONE}.",
            "Member profile: {NAME}, email {EMAIL}, phone {PHONE}",
            "KYC: {NAME}, DOB {DATE}, SSN {SSN}, address {ADDRESS}",
            "Customer {NAME} has been verified. SSN: {SSN}. Date of birth: {DATE}. Address: {ADDRESS}. Account is now active.",
            "New customer registration: {NAME}, SSN: {SSN}, DOB: {DATE}. Identity verification complete.",
            "KYC verification complete for {NAME}. SSN: {SSN}, DOB: {DATE}, address: {ADDRESS}. Please review.",
        ]
    },
    "internal_strategy": {
        "name": "Internal Strategy/M&A",
        "slot_types": ["COMPANY", "AMOUNT", "NAME", "DATE"],
        "primary_slot": "COMPANY",
        "patterns": INTERNAL_STRATEGY_PATTERNS,
        "base_templates": [
            "Board approved acquisition of {COMPANY} for {AMOUNT}",
            "Q{QUARTER} revenue: {AMOUNT}. Not yet public.",
            "M&A target: {COMPANY}, valuation {AMOUNT}",
            "Restructuring: savings {AMOUNT}. Effective {DATE}.",
        ]
    },
    "certificate_tls": {
        "name": "Certificate/TLS Key Material",
        "slot_types": ["PASSWORD", "DOMAIN", "API_KEY", "DATE"],
        "primary_slot": "PASSWORD",
        "patterns": CERTIFICATE_TLS_PATTERNS,
        "base_templates": [
            "SSL certificate for {DOMAIN}: private key passphrase {PASSWORD}",
            "Wildcard cert *.{DOMAIN}: PKCS12 password {PASSWORD}",
            "JKS keystore password: {PASSWORD}",
            "Root CA key passphrase: {PASSWORD}",
            "Code signing cert passphrase: {PASSWORD}",
        ]
    },
    "encryption_keys": {
        "name": "Encryption Keys/Vault Secrets",
        "slot_types": ["API_KEY", "PASSWORD", "URL"],
        "primary_slot": "API_KEY",
        "patterns": ENCRYPTION_KEYS_PATTERNS,
        "base_templates": [
            "HashiCorp Vault token: {API_KEY}",
            "Vault root token: {API_KEY}, unseal key: {PASSWORD}",
            "GPG passphrase: {PASSWORD}",
            "VAULT_TOKEN={API_KEY}\nVAULT_ADDR={URL}",
            "KMS master key: {PASSWORD}",
        ]
    },
    "oauth_sso": {
        "name": "OAuth/SSO Secrets",
        "slot_types": ["CLIENT_ID", "CLIENT_SECRET", "URL", "API_KEY", "TENANT_ID"],
        "primary_slot": "CLIENT_SECRET",
        "patterns": OAUTH_SSO_PATTERNS,
        "base_templates": [
            "OAuth client ID: {CLIENT_ID}, secret: {CLIENT_SECRET}",
            "SSO config: client {CLIENT_ID}, secret {CLIENT_SECRET}",
            "OIDC client secret: {CLIENT_SECRET}. Discovery URL: {URL}",
            "SAML signing cert password: {PASSWORD}",
            "JWT signing key: {API_KEY}",
        ]
    },
    "database_connection": {
        "name": "Database Connection Strings",
        "slot_types": ["PASSWORD", "USERNAME", "HOSTNAME", "PORT", "DBNAME"],
        "primary_slot": "PASSWORD",
        "patterns": DATABASE_CONNECTION_PATTERNS,
        "base_templates": [
            "DATABASE_URL=postgresql://{USERNAME}:{PASSWORD}@{HOSTNAME}:{PORT}/{DBNAME}",
            "jdbc:mysql://{HOSTNAME}:{PORT}/{DBNAME}?user={USERNAME}&password={PASSWORD}",
            "Connection: host={HOSTNAME} dbname={DBNAME} user={USERNAME} password={PASSWORD}",
            "MongoDB: mongodb://{USERNAME}:{PASSWORD}@{HOSTNAME}:{PORT}/{DBNAME}",
            "The database is available at {HOSTNAME}:{PORT}. Database name: {DBNAME}. Login with {USERNAME} and password {PASSWORD}.",
            "Database credentials have been updated. Host: {HOSTNAME}, user: {USERNAME}, password: {PASSWORD}. Database: {DBNAME}.",
            "Please connect to the database at {HOSTNAME}:{PORT} using username {USERNAME} and password {PASSWORD}.",
        ]
    },
    "vendor_partner": {
        "name": "Vendor/Partner Access",
        "slot_types": ["API_KEY", "PASSWORD", "URL", "USERNAME", "CLIENT_ID", "CLIENT_SECRET"],
        "primary_slot": "API_KEY",
        "patterns": VENDOR_PARTNER_PATTERNS,
        "base_templates": [
            "Vendor API key: {API_KEY}. Endpoint: {URL}",
            "Partner portal: {URL}, login {USERNAME}/{PASSWORD}",
            "Third-party integration: API key {API_KEY}",
            "Vendor SFTP: user {USERNAME}, password {PASSWORD}",
            "The vendor API has been configured. Endpoint: {URL}. API key: {API_KEY}. Contact vendor for support.",
            "Vendor integration is live. API key: {API_KEY}. Endpoint: {URL}. Please verify connectivity.",
            "Access to the partner portal at {URL} has been provisioned. Username: {USERNAME}, password: {PASSWORD}.",
        ]
    },
    "saas_credentials": {
        "name": "SaaS Platform Credentials",
        "slot_types": ["PASSWORD", "API_KEY", "USERNAME", "URL", "EMAIL"],
        "primary_slot": "PASSWORD",
        "patterns": SAAS_CREDENTIALS_PATTERNS,
        "base_templates": [
            "Salesforce admin: {EMAIL} / {PASSWORD}",
            "Jira API token: {API_KEY}",
            "Slack bot token: {API_KEY}",
            "Datadog API key: {API_KEY}",
            "ServiceNow admin: {USERNAME} / {PASSWORD}",
        ]
    },
}


# ============================================================================
# ADVANCED TEMPLATE GENERATOR
# ============================================================================

@dataclass
class GeneratorConfig:
    """Configuration for template generation."""
    target_count: int = 100000
    max_count: int = 2000000
    include_case_variations: bool = True
    include_punctuation_variations: bool = True
    include_structural_variations: bool = True
    dedup_enabled: bool = True
    random_seed: Optional[int] = None


class AdvancedTemplateGenerator:
    """
    Generates massive numbers of unique templates through multiple strategies.
    """

    def __init__(self, domain: str, config: Optional[GeneratorConfig] = None):
        if domain not in DOMAIN_CONFIGS:
            raise ValueError(f"Unknown domain: {domain}")

        self.domain = domain
        self.domain_config = DOMAIN_CONFIGS[domain]
        self.config = config or GeneratorConfig()

        if self.config.random_seed is not None:
            random.seed(self.config.random_seed)

        self._seen_hashes: Set[str] = set()
        self._templates: List[str] = []

    def _hash(self, text: str) -> str:
        """Create hash for deduplication."""
        normalized = re.sub(r'\s+', ' ', text.lower().strip())
        return hashlib.md5(normalized.encode()).hexdigest()[:16]

    def _add_template(self, template: str) -> bool:
        """Add template if unique and well-formed. Returns True if added."""
        if not template or len(template) < 10:
            return False

        # Reject stacked formality prefixes (e.g. "Please please navigate")
        if self._has_stacked_formality(template):
            return False

        if self.config.dedup_enabled:
            h = self._hash(template)
            if h in self._seen_hashes:
                return False
            self._seen_hashes.add(h)

        self._templates.append(template)
        return True

    # Formality phrases that should never be stacked (lowercased for matching)
    _FORMALITY_PHRASES = (
        "please ", "kindly ", "we request that you ",
        "you are required to ", "you are requested to ",
        "you must ", "you should ",
        "we ask that you ", "it is required that you ",
        "for security purposes, ", "for your security, ",
        "important: ", "action required: ", "notice: ",
    )

    def _clean_template(self, template: str) -> str:
        """Clean up template formatting."""
        # Remove extra whitespace
        template = re.sub(r'\s+', ' ', template).strip()
        # Fix punctuation spacing
        template = re.sub(r'\s+([.,!?])', r'\1', template)
        template = re.sub(r'([.,!?])\s*([.,!?])', r'\1', template)
        # Fix double spaces after punctuation
        template = re.sub(r'([.,!?])\s{2,}', r'\1 ', template)
        return template

    # Verb-expecting prefixes: these only make sense before a verb/action
    _VERB_EXPECTING_PREFIXES = (
        "please ", "kindly ", "we request that you ",
        "you are required to ", "you are requested to ",
        "you must ", "you should ",
        "we ask that you ", "it is required that you ",
    )
    # Words that indicate a noun phrase (not a verb) follows
    _NON_VERB_STARTERS = (
        "the ", "a ", "an ", "your ", "our ", "their ", "its ",
        "this ", "that ", "these ", "those ",
    )
    # Regex: next word starts with uppercase = likely a proper noun, not a verb
    _PROPER_NOUN_RE = re.compile(r'^[A-Z][a-zA-Z]')

    def _has_stacked_formality(self, text: str) -> bool:
        """Detect garbled formality: doubled prefixes or verb-expecting prefix
        followed by an article/noun instead of a verb, anywhere in template."""
        tl = text.lower()
        # Check at start and after sentence boundaries (". ", "! ", "? ")
        positions = [0]
        for m in re.finditer(r'[.!?]\s+', tl):
            positions.append(m.end())
        for pos in positions:
            segment = tl[pos:]
            for prefix in self._FORMALITY_PHRASES:
                if segment.startswith(prefix):
                    rest = segment[len(prefix):]
                    # Reject stacked formality
                    if any(rest.startswith(p) for p in self._FORMALITY_PHRASES):
                        return True
            # Reject verb-expecting prefix + article/determiner or proper noun
            for prefix in self._VERB_EXPECTING_PREFIXES:
                if segment.startswith(prefix):
                    rest = segment[len(prefix):]
                    if any(rest.startswith(w) for w in self._NON_VERB_STARTERS):
                        return True
                    # Check against the ORIGINAL text (not lowered) for proper nouns
                    orig_rest = text[pos + len(prefix):]
                    if self._PROPER_NOUN_RE.match(orig_rest):
                        return True
        return False

    # -------------------------------------------------------------------------
    # Strategy 1: Base template expansion
    # -------------------------------------------------------------------------
    def _generate_from_base(self) -> int:
        """Generate from base templates with variations."""
        count = 0
        base_templates = self.domain_config.get("base_templates", [])

        for template in base_templates:
            if self._add_template(template):
                count += 1

        return count

    # -------------------------------------------------------------------------
    # Strategy 2: Pattern-based combinatorial expansion
    # -------------------------------------------------------------------------
    def _generate_from_patterns(self, max_per_pattern: int = 10000) -> int:
        """Generate templates from structural patterns."""
        count = 0
        patterns = self.domain_config.get("patterns", PASSWORD_RESET_PATTERNS)

        for pattern in patterns:
            generated = 0

            # Identify placeholders
            placeholders = re.findall(r'\{([A-Z_]+)\}', pattern)

            # Build variation lists for each placeholder type
            variations = self._get_placeholder_variations(placeholders)

            if not variations:
                if self._add_template(pattern):
                    count += 1
                continue

            # Generate combinations
            keys = list(variations.keys())
            value_lists = [variations[k] for k in keys]

            for combo in product(*value_lists):
                if generated >= max_per_pattern:
                    break

                result = pattern
                for key, value in zip(keys, combo):
                    # Replace placeholder with value
                    result = result.replace("{" + key + "}", value, 1)

                result = self._clean_template(result)
                if self._add_template(result):
                    count += 1
                    generated += 1

        return count

    def _get_placeholder_variations(self, placeholders: List[str]) -> Dict[str, List[str]]:
        """Get variations for each placeholder type."""
        variations = {}

        for ph in placeholders:
            if ph in ["PASSWORD", "URL", "API_KEY", "NAME", "SALARY", "DATE",
                      "SSN", "EMPLOYEE_ID", "EMAIL", "TOKEN", "SECRET",
                      "ACCESS_KEY", "SECRET_KEY", "SSH_KEY",
                      "ACCOUNT_ID", "ACCOUNT", "AMOUNT", "ROUTING",
                      "CLIENT_ID", "CLIENT_SECRET", "TENANT_ID",
                      "MRN", "CODE", "COMPANY", "DEPARTMENT",
                      "DOMAIN", "ARN", "PHONE", "ADDRESS",
                      "SSN_LAST4", "CARD_LAST4", "RATE", "YEAR", "QUARTER",
                      "DOSAGE", "MEDICATION"]:
                # These are slot placeholders - keep as is
                variations[ph] = ["{" + ph + "}"]

            elif ph == "PREFIX":
                variations[ph] = FORMALITY_PREFIXES[:15]

            elif ph == "VERB":
                all_verbs = []
                for verb_list in ACTION_VERBS.values():
                    all_verbs.extend(verb_list[:5])
                variations[ph] = list(set(all_verbs))[:20]

            elif ph in ["URL_TERM"]:
                all_terms = []
                for term_list in URL_TERMS.values():
                    all_terms.extend(term_list[:4])
                variations[ph] = list(set(all_terms))[:15]

            elif ph in ["PW_TERM"]:
                all_terms = []
                for term_list in PASSWORD_TERMS.values():
                    all_terms.extend(term_list[:4])
                variations[ph] = list(set(all_terms))[:15]

            elif ph == "ACTION":
                variations[ph] = RESET_ACTIONS[:15]

            elif ph == "IMMEDIACY":
                variations[ph] = IMMEDIACY_TERMS[:10]

            elif ph == "CLOSING":
                variations[ph] = CLOSING_PHRASES[:10]

            elif ph == "PW_CONTEXT":
                variations[ph] = PW_CONTEXT_PHRASES[:12]

            elif ph == "CONNECTOR":
                variations[ph] = CONNECTORS[:8]

            elif ph == "TIME":
                variations[ph] = TIME_CONSTRAINTS[:8]

            # HR-specific
            elif ph == "NAME_PREFIX":
                variations[ph] = ["Employee ", "Staff member ", "Team member ", ""]

            elif ph == "SALARY_ACTION":
                variations[ph] = ["salary adjusted", "compensation set", "pay increased",
                                  "earnings changed", "base salary set"]

            elif ph == "DATE_CTX":
                variations[ph] = ["effective", "starting", "as of", "beginning", "from"]

            # Infrastructure credential-specific
            elif ph == "SERVICE":
                variations[ph] = SERVICE_TERMS[:20]

            elif ph == "DBTYPE":
                variations[ph] = DBTYPE_TERMS[:15]

            elif ph == "USERNAME":
                variations[ph] = USERNAME_TERMS[:15]

            elif ph == "HOSTNAME":
                variations[ph] = HOSTNAME_TERMS[:12]

            elif ph == "INFRA_CONTEXT":
                variations[ph] = INFRA_CONTEXT_PHRASES[:10]

            elif ph == "CRED_JOIN":
                variations[ph] = CREDENTIAL_JOINERS[:10]

            elif ph == "DBNAME":
                variations[ph] = ["production", "staging", "main", "app", "mydb",
                                  "webapp", "core", "primary"]

            elif ph == "PORT":
                variations[ph] = ["5432", "3306", "27017", "6379", "1433",
                                  "3307", "5433", "8080", "443"]

            elif ph == "NUMBER":
                variations[ph] = ["12345", "67890", "11111", "99999", "54321"]

            # Cloud AWS
            elif ph == "AWS_SERVICE":
                variations[ph] = AWS_SERVICES[:12]
            elif ph == "AWS_REGION":
                variations[ph] = AWS_REGIONS

            # Cloud Azure
            elif ph == "AZURE_SERVICE":
                variations[ph] = AZURE_SERVICES[:10]
            elif ph == "AZURE_RESOURCE":
                variations[ph] = AZURE_RESOURCE_TYPES[:8]

            # Network/VPN
            elif ph == "VPN_TYPE":
                variations[ph] = VPN_TYPES[:8]
            elif ph == "WIFI_SEC":
                variations[ph] = WIFI_SECURITY
            elif ph == "NETWORK_DEVICE":
                variations[ph] = NETWORK_DEVICES[:8]

            # CI/CD
            elif ph == "CICD_PLATFORM":
                variations[ph] = CICD_PLATFORMS[:10]
            elif ph == "REGISTRY":
                variations[ph] = REGISTRY_TYPES[:8]

            # Email/SMTP
            elif ph == "SMTP_SVR":
                variations[ph] = SMTP_SERVERS[:8]
            elif ph == "EMAIL_PROTO":
                variations[ph] = EMAIL_PROTOCOLS

            # Financial
            elif ph == "BANK":
                variations[ph] = BANK_NAMES[:10]
            elif ph == "TRANSACTION":
                variations[ph] = TRANSACTION_TYPES[:6]

            # Legal
            elif ph == "LEGAL_TYPE":
                variations[ph] = LEGAL_TYPES[:10]
            elif ph == "LEGAL_PARTY":
                variations[ph] = LEGAL_PARTIES[:6]

            # Medical
            elif ph == "FACILITY":
                variations[ph] = MEDICAL_FACILITIES[:6]
            elif ph == "DIAGNOSIS_CODE":
                variations[ph] = DIAGNOSIS_CODES
            elif ph == "MEDICATION":
                variations[ph] = ["{MEDICATION}"]
            elif ph == "DOSAGE":
                variations[ph] = ["{DOSAGE}"]

            # Customer PII
            elif ph == "PII_DOC":
                variations[ph] = PII_DOCUMENT_TYPES[:6]

            # Internal Strategy
            elif ph == "MEETING":
                variations[ph] = MEETING_TYPES[:8]
            elif ph == "STRATEGY_ACTION":
                variations[ph] = STRATEGY_ACTIONS[:8]

            # Certificate/TLS
            elif ph == "CERT_TYPE":
                variations[ph] = CERT_TYPES[:8]
            elif ph == "CERT_FORMAT":
                variations[ph] = CERT_FORMATS

            # Encryption
            elif ph == "ENCRYPTION_TYPE":
                variations[ph] = ENCRYPTION_TYPES[:8]
            elif ph == "VAULT_PATH":
                variations[ph] = VAULT_PATHS

            # OAuth/SSO
            elif ph == "OAUTH_PROVIDER":
                variations[ph] = OAUTH_PROVIDERS[:8]

            # Vendor/Partner
            elif ph == "VENDOR":
                variations[ph] = VENDOR_NAMES[:8]

            # SaaS
            elif ph == "SAAS_PLATFORM":
                variations[ph] = SAAS_PLATFORMS[:12]

        return variations

    # -------------------------------------------------------------------------
    # Strategy 3: Linguistic variations
    # -------------------------------------------------------------------------
    def _generate_linguistic_variations(self, max_variations: int = 50000) -> int:
        """Generate variations through linguistic transformations."""
        count = 0
        existing = self._templates.copy()

        for template in existing:
            if count >= max_variations:
                break

            # Protect slot placeholders from synonym replacement:
            # Temporarily replace {SLOT} tokens with opaque markers,
            # do synonym substitution, then restore them.
            slot_map = {}
            protected = template
            for i, m in enumerate(re.finditer(r'\{[A-Z_]+\}', template)):
                marker = f"\x00SLOT{i}\x00"
                slot_map[marker] = m.group()
                protected = protected.replace(m.group(), marker, 1)

            # Synonym replacement for common terms
            # Words that should not be replaced when used as adjectives
            # (e.g. "reset password" — "reset" is an adjective here)
            _adj_nouns = r'(?:\s+(?:password|passcode|credential|code|key|token|access))'
            for original, replacements in self._get_synonym_map().items():
                for replacement in replacements[:5]:
                    # For words like "reset"/"default" that can be adj or verb,
                    # avoid replacing when directly before a noun
                    if original in ("reset", "default"):
                        pattern = r'\b' + re.escape(original) + r'\b(?!' + _adj_nouns + r')'
                    else:
                        pattern = r'\b' + re.escape(original) + r'\b'
                    variant = re.sub(
                        pattern,
                        replacement,
                        protected,
                        flags=re.IGNORECASE
                    )
                    if variant != protected:
                        # Restore slot placeholders
                        restored = variant
                        for marker, slot in slot_map.items():
                            restored = restored.replace(marker, slot)
                        restored = self._clean_template(restored)
                        if self._add_template(restored):
                            count += 1

            # Active/passive voice transformation (simplified)
            if "is set to" in template.lower():
                variant = template.replace("is set to", "has been set to")
                if self._add_template(variant):
                    count += 1

            if "must be" in template.lower():
                variant = template.replace("must be", "should be")
                if self._add_template(variant):
                    count += 1
                variant = template.replace("must be", "needs to be")
                if self._add_template(variant):
                    count += 1

        return count

    def _get_synonym_map(self) -> Dict[str, List[str]]:
        """Get synonym mapping for common terms."""
        base = {
            "password": ["passcode", "credential", "access code"],
            "navigate": ["go", "proceed", "head"],
            "visit": ["access", "open", "go to"],
            "click": ["select", "choose", "press"],
            "immediately": ["right away", "promptly", "at once"],
            "temporary": ["temp", "initial", "one-time"],
            "default": ["initial", "assigned", "generated"],
            "reset": ["change", "update", "modify"],
            "portal": ["site", "page", "website"],
            "login": ["sign in", "log in", "authenticate"],
        }

        if self.domain == "infrastructure_credentials":
            base.update({
                "server": ["host", "machine", "instance", "node"],
                "database": ["DB", "datastore", "data store"],
                "admin": ["administrator", "root", "superuser"],
                "credentials": ["login details", "access details", "auth details"],
                "username": ["user", "login", "account"],
                "production": ["prod", "live", "primary"],
                "connect": ["access", "log in", "authenticate"],
            })

        if self.domain in ("cloud_aws", "cloud_azure"):
            base.update({
                "credentials": ["creds", "access details", "auth details"],
                "secret": ["secret key", "private key", "auth secret"],
                "account": ["subscription", "project", "tenant"],
            })

        if self.domain in ("network_vpn",):
            base.update({
                "gateway": ["server", "endpoint", "concentrator"],
                "connect": ["log in", "authenticate", "access"],
                "password": ["passphrase", "PSK", "pre-shared key", "credential"],
            })

        if self.domain in ("ci_cd_devops",):
            base.update({
                "token": ["key", "secret", "credential", "PAT"],
                "deploy": ["release", "publish", "push"],
                "pipeline": ["workflow", "job", "build"],
            })

        if self.domain in ("financial_banking",):
            base.update({
                "transfer": ["payment", "wire", "remittance", "disbursement"],
                "account": ["acct", "deposit account", "bank account"],
            })

        if self.domain in ("medical_hipaa",):
            base.update({
                "patient": ["client", "member", "individual"],
                "diagnosis": ["condition", "finding", "assessment"],
                "prescription": ["medication", "Rx", "order"],
            })

        if self.domain in ("saas_credentials", "vendor_partner"):
            base.update({
                "token": ["API key", "secret", "auth token"],
                "login": ["sign in", "authenticate", "access"],
                "admin": ["administrator", "super admin", "owner"],
            })

        return base

    # -------------------------------------------------------------------------
    # Strategy 4: Structural transformations
    # -------------------------------------------------------------------------
    def _generate_structural_variations(self, max_variations: int = 30000) -> int:
        """Generate variations through structural transformations."""
        count = 0
        existing = self._templates.copy()

        for template in existing:
            if count >= max_variations:
                break

            # Sentence reordering
            sentences = re.split(r'(?<=[.!?])\s+', template)
            if len(sentences) >= 2:
                # Swap sentences
                for i in range(len(sentences) - 1):
                    reordered = sentences.copy()
                    reordered[i], reordered[i + 1] = reordered[i + 1], reordered[i]
                    variant = ' '.join(reordered)
                    variant = self._clean_template(variant)
                    if self._add_template(variant):
                        count += 1

            # Add/remove politeness prefixes
            # Known formality prefixes that should not be stacked
            _formality_starts = (
                "please ", "kindly ", "we request that you ",
                "you are required to ", "you must ", "you should ",
                "we ask that you ", "it is required that you ",
                "for security purposes, ", "for your security, ",
                "important: ", "action required: ", "notice: ",
            )
            for prefix in ["Please ", "Kindly ", ""]:
                if template.startswith("Please "):
                    body = template[7:]
                elif template.startswith("Kindly "):
                    body = template[7:]
                else:
                    if prefix:
                        # Don't try to lowercase — it corrupts proper nouns
                        # (Docker→docker, Slack→slack, etc.).  The stacked-
                        # formality filter already rejects "Please The..." etc.
                        body = template
                    else:
                        continue

                # Skip if adding a prefix on top of another formality phrase
                if prefix and body.lower().startswith(_formality_starts):
                    continue

                variant = prefix + body
                variant = self._clean_template(variant)
                if variant != template and self._add_template(variant):
                    count += 1

            # Punctuation variations
            if template.endswith('.'):
                if self._add_template(template[:-1] + '!'):
                    count += 1
            elif template.endswith('!'):
                if self._add_template(template[:-1] + '.'):
                    count += 1

        return count

    # -------------------------------------------------------------------------
    # Strategy 5: Contextual wrapping (email framing, urgency, clause insertion)
    # -------------------------------------------------------------------------
    # Domains where credential-change language makes sense
    _CREDENTIAL_DOMAINS = {
        "it_password", "infrastructure_credentials", "cloud_aws",
        "cloud_azure", "network_vpn", "ci_cd_devops", "email_smtp",
        "oauth_sso", "database_connection", "saas_credentials",
        "vendor_partner", "api_developer", "certificate_tls",
        "encryption_keys",
    }

    def _generate_contextual_wrapping(self, max_variations: int = 25000) -> int:
        """Generate variations by wrapping existing templates with contextual framing."""
        count = 0
        existing = self._templates.copy()

        # Skip env-var / connection-string style templates
        skip_prefixes = (
            "DB_HOST=", "DB_USER=", "DB_PASS=", "DATABASE_URL=",
            "AWS_ACCESS_KEY", "AZURE_TENANT", "AZURE_CLIENT",
            "SMTP_HOST=", "SMTP_PORT=", "SMTP_USER=", "SMTP_PASS=",
            "VAULT_TOKEN=", "VAULT_ADDR=", "DOCKER_USERNAME=",
            "DOCKER_PASSWORD=", "NPM_TOKEN=", "PYPI_TOKEN=",
            "SAAS_TOKEN=", "SAAS_URL=",
        )
        skip_patterns = (
            "jdbc:", "://{", "DSN:", "ODBC:", "Data Source=",
            "{USERNAME}:{PASSWORD}", "={", "Connection string:",
            "aws configure", "az login", "curl -H",
        )

        email_framings = [
            "Dear employee, ", "Hi team, ",
            "This is an automated notification. ", "FYI - ",
            "As discussed, ", "Per your request, ",
        ]
        urgency_suffixes = [
            " This must be completed within 24 hours.",
            " This is time-sensitive.",
            " Please action immediately.",
        ]
        # Only add "account lockout" suffix for credential domains
        if self.domain in self._CREDENTIAL_DOMAINS:
            urgency_suffixes.append(
                " Failure to comply may result in account lockout."
            )

        clause_insertions = [
            " which must be changed immediately",
            " which expires in 24 hours",
            " and must be updated on first login",
        ]
        # Clause insertions only make sense for credential/key domains
        use_clause_insertions = self.domain in self._CREDENTIAL_DOMAINS

        # Determine available transforms: always 0 (email) and 1 (urgency)
        available_transforms = [0, 1]
        if use_clause_insertions:
            available_transforms.append(2)

        random.shuffle(existing)

        for template in existing:
            if count >= max_variations:
                break

            # Skip env-var style templates
            if any(template.startswith(p) for p in skip_prefixes):
                continue
            if any(p in template for p in skip_patterns):
                continue

            transform = random.choice(available_transforms)

            if transform == 0:
                # Email framing
                prefix = random.choice(email_framings)
                # Don't try to lowercase — it corrupts proper nouns
                # (Docker→docker, Slack→slack, Settlement→settlement, etc.)
                variant = prefix + template
            elif transform == 1:
                # Urgency suffix
                suffix = random.choice(urgency_suffixes)
                if template.endswith('.'):
                    variant = template[:-1] + suffix
                elif template.endswith('!'):
                    variant = template[:-1] + suffix
                else:
                    variant = template + suffix
            else:
                # Clause insertion after first sentence
                sentences = re.split(r'(?<=[.!?])\s+', template, maxsplit=1)
                if len(sentences) >= 2:
                    clause = random.choice(clause_insertions)
                    first = sentences[0]
                    if first.endswith('.'):
                        first = first[:-1] + clause + '.'
                    elif first.endswith('!'):
                        first = first[:-1] + clause + '!'
                    else:
                        first = first + clause
                    variant = first + ' ' + sentences[1]
                else:
                    # Single sentence - append clause before final punctuation
                    clause = random.choice(clause_insertions)
                    if template.endswith('.'):
                        variant = template[:-1] + clause + '.'
                    elif template.endswith('!'):
                        variant = template[:-1] + clause + '!'
                    else:
                        variant = template + clause
            variant = self._clean_template(variant)
            if self._add_template(variant):
                count += 1

        return count

    # -------------------------------------------------------------------------
    # Strategy 6: Case variations
    # -------------------------------------------------------------------------
    def _generate_case_variations(self, max_variations: int = 20000) -> int:
        """Generate case variations."""
        if not self.config.include_case_variations:
            return 0

        count = 0
        existing = self._templates.copy()

        for template in existing:
            if count >= max_variations:
                break

            # Lowercase (preserve placeholders)
            def lowercase_preserve_placeholders(text):
                parts = re.split(r'(\{[A-Z_]+\})', text)
                return ''.join(
                    p if p.startswith('{') else p.lower()
                    for p in parts
                )

            variant = lowercase_preserve_placeholders(template)
            if self._add_template(variant):
                count += 1

            # Title case for sentences
            sentences = re.split(r'(?<=[.!?])\s+', template)
            titled = ' '.join(s.capitalize() if not s.startswith('{') else s for s in sentences)
            if self._add_template(titled):
                count += 1

        return count

    # -------------------------------------------------------------------------
    # Strategy 7: Randomized combination synthesis
    # -------------------------------------------------------------------------
    def _generate_random_combinations(self, target_remaining: int) -> int:
        """Generate random combinations by sampling patterns with random placeholder values."""
        count = 0
        patterns = self.domain_config.get("patterns", [])
        if not patterns:
            return 0

        attempts = 0
        max_attempts = target_remaining * 5

        while count < target_remaining and attempts < max_attempts:
            attempts += 1

            pattern = random.choice(patterns)
            placeholders = re.findall(r'\{([A-Z_]+)\}', pattern)
            variations = self._get_placeholder_variations(placeholders)

            if not variations:
                continue

            result = pattern
            for ph in placeholders:
                if ph in variations:
                    result = result.replace("{" + ph + "}", random.choice(variations[ph]), 1)

            result = self._clean_template(result)
            if len(result) >= 10 and self._add_template(result):
                count += 1

        return count

    # -------------------------------------------------------------------------
    # Main generation method
    # -------------------------------------------------------------------------
    def generate(self, count: Optional[int] = None) -> List[str]:
        """
        Generate templates using all strategies.

        Args:
            count: Target number of templates (default from config)

        Returns:
            List of unique template strings
        """
        target = count or self.config.target_count
        target = min(target, self.config.max_count)

        self._templates = []
        self._seen_hashes = set()

        print(f"\n[+] Generating templates for: {self.domain_config['name']}")
        print(f"    Target: {target:,}")

        # Strategy 1: Base templates
        n = self._generate_from_base()
        print(f"    Base templates: {n:,} (total: {len(self._templates):,})")

        # Strategy 2: Pattern-based
        if len(self._templates) < target:
            n = self._generate_from_patterns(max_per_pattern=max(1000, target // 20))
            print(f"    Pattern-based: {n:,} (total: {len(self._templates):,})")

        # Strategy 3: Linguistic variations
        if len(self._templates) < target:
            n = self._generate_linguistic_variations(max_variations=target // 3)
            print(f"    Linguistic variations: {n:,} (total: {len(self._templates):,})")

        # Strategy 4: Structural variations
        if len(self._templates) < target:
            n = self._generate_structural_variations(max_variations=target // 4)
            print(f"    Structural variations: {n:,} (total: {len(self._templates):,})")

        # Strategy 5: Contextual wrapping (email framing, urgency, clause insertion)
        if len(self._templates) < target:
            n = self._generate_contextual_wrapping(max_variations=target // 4)
            print(f"    Contextual wrapping: {n:,} (total: {len(self._templates):,})")

        # Strategy 6: Case variations
        if len(self._templates) < target:
            n = self._generate_case_variations(max_variations=target // 5)
            print(f"    Case variations: {n:,} (total: {len(self._templates):,})")

        # Strategy 7: Random synthesis to fill remaining
        if len(self._templates) < target:
            remaining = target - len(self._templates)
            n = self._generate_random_combinations(remaining)
            print(f"    Random synthesis: {n:,} (total: {len(self._templates):,})")

        print(f"\n    Final count: {len(self._templates):,}")

        # Shuffle so any prefix slice is representative of all strategies
        result = self._templates[:target]
        random.shuffle(result)
        return result

    def generate_for_chunk_position(
        self,
        position: str,
        count: int = 10000
    ) -> List[str]:
        """
        Generate templates optimized for specific chunk position.

        Args:
            position: "first", "middle", or "last"
            count: Number of templates to generate

        Returns:
            Templates weighted for the specified position
        """
        all_templates = self.generate(count * 2)

        # Filter/weight based on position
        weighted = []

        for template in all_templates:
            score = 1.0
            template_lower = template.lower()

            if position == "first":
                # First chunks often have greetings, intros
                if any(t in template_lower for t in ["please", "dear", "hello", "welcome"]):
                    score *= 1.3
                if any(t in template_lower for t in ["thank", "regards", "sincerely"]):
                    score *= 0.7

            elif position == "last":
                # Last chunks often have closings
                if any(t in template_lower for t in ["thank", "regards", "contact", "support"]):
                    score *= 1.3
                if any(t in template_lower for t in ["dear", "hello", "welcome"]):
                    score *= 0.7

            elif position == "middle":
                # Middle chunks are more neutral
                if any(t in template_lower for t in ["following", "below", "details"]):
                    score *= 1.2

            weighted.append((template, score))

        # Sort by score and return top
        weighted.sort(key=lambda x: x[1], reverse=True)
        return [t for t, _ in weighted[:count]]


# ============================================================================
# DOMAIN DETECTION (requires torch + transformers)
# ============================================================================

# Domain detection signatures -- representative phrases for each domain,
# used to classify target embeddings via cosine similarity.
DOMAIN_SIGNATURES = {
    "it_password": [
        "password reset portal login",
        "temporary password first login",
        "navigate to URL and click forgot password",
        "SSO portal access code credential",
        "reset your password at the login page",
        "default password after resetting must be changed immediately",
    ],
    "infrastructure_credentials": [
        "production database server admin username password",
        "server admin root credentials connection string",
        "database host port username password",
        "VPN gateway kubernetes cluster SSH key",
        "DB_HOST DB_USER DB_PASS connection",
        "default credentials for the server root password",
    ],
    "hr_employee": [
        "employee salary compensation annually effective",
        "SSN employee ID benefits enrollment",
        "personal info address phone emergency contact",
        "new hire starting salary date",
        "medical claim diagnosis HIPAA patient",
        "compensation package base salary bonus",
    ],
    "api_developer": [
        "API endpoint key bearer token authorization",
        "service URL API key authentication token",
        "production API auth secret key",
        "curl authorization bearer access token",
        "endpoint requires token refresh secret",
        "service account credentials API key",
    ],
    "cloud_aws": [
        "AWS access key secret key IAM credentials",
        "AWS account ID access key secret key region",
        "AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY environment",
        "S3 EC2 Lambda RDS IAM credentials production",
        "ARN IAM user access key secret us-east-1",
        "aws configure profile access key secret region",
    ],
    "cloud_azure": [
        "Azure tenant ID client ID client secret service principal",
        "AZURE_TENANT_ID AZURE_CLIENT_ID AZURE_CLIENT_SECRET",
        "Azure AD app registration client secret",
        "Azure Key Vault SAS token connection string",
        "Azure SQL Server password connection string",
        "az login service principal tenant client secret",
    ],
    "network_vpn": [
        "VPN gateway username password OpenVPN WireGuard",
        "WiFi network WPA2 password passphrase SSID",
        "firewall admin console management credentials",
        "IPSec pre-shared key tunnel gateway VPN",
        "RADIUS shared secret network access control",
        "SNMP community string router switch firewall",
    ],
    "ci_cd_devops": [
        "GitHub personal access token Jenkins pipeline",
        "Docker registry login username password push",
        "CI CD pipeline secret token deploy key",
        "Terraform Cloud API token Ansible vault password",
        "NPM_TOKEN PYPI_TOKEN package registry auth",
        "GitLab CI runner token deploy key webhook secret",
    ],
    "email_smtp": [
        "SMTP server port username password outgoing mail",
        "SMTP_HOST SMTP_PORT SMTP_USER SMTP_PASS",
        "SendGrid Mailgun API key email service",
        "Office 365 SMTP email password app password",
        "IMAP POP3 Exchange mailbox credentials login",
        "email relay server authentication password",
    ],
    "financial_banking": [
        "wire transfer ACH routing number account number bank",
        "bank account routing number direct deposit payment",
        "SWIFT code beneficiary account amount transfer",
        "invoice payment amount payable account bank",
        "payroll direct deposit routing account salary",
        "treasury disbursement wire transfer amount account",
    ],
    "legal_confidential": [
        "NDA settlement agreement confidential amount signed",
        "acquisition merger valuation closing date agreement",
        "non-disclosure settlement confidential legal agreement",
        "board approved acquire company valuation amount",
        "termination agreement severance amount effective date",
        "pending litigation reserve settlement confidential",
    ],
    "medical_hipaa": [
        "patient name MRN medical record number diagnosis",
        "HIPAA patient SSN medical record prescription",
        "ICD-10 CPT diagnosis code patient admission",
        "discharge summary patient MRN admitted diagnosis",
        "prescription medication dosage patient doctor",
        "lab results radiology patient record department",
    ],
    "customer_pii": [
        "customer SSN social security number date of birth",
        "account holder name address phone email credit card",
        "KYC identity verification SSN DOB address",
        "member profile email phone address subscriber",
        "credit card number expiration billing address name",
        "customer data export name email phone address PII",
    ],
    "internal_strategy": [
        "board meeting approved acquisition valuation confidential",
        "quarterly revenue earnings not yet public embargo",
        "M&A pipeline target company valuation LOI",
        "restructuring headcount layoff savings effective date",
        "insider information patent settlement announce date",
        "executive compensation CEO total comp board approved",
    ],
    "certificate_tls": [
        "SSL TLS certificate private key passphrase domain",
        "wildcard certificate PKCS12 PEM key password",
        "JKS keystore password certificate signing key",
        "root CA intermediate certificate private key passphrase",
        "code signing certificate key password expiration",
        "Let's Encrypt certificate account key PFX export",
    ],
    "encryption_keys": [
        "HashiCorp Vault token root unseal key secret",
        "KMS master key encryption AES-256 RSA GPG",
        "VAULT_TOKEN VAULT_ADDR secret data production",
        "GPG PGP passphrase encryption key signing",
        "SOPS age sealed secrets encryption key",
        "LUKS BitLocker disk encryption passphrase volume",
    ],
    "oauth_sso": [
        "OAuth client ID client secret OIDC SSO",
        "Okta Auth0 Azure AD SSO SAML configuration",
        "OIDC discovery well-known client secret redirect",
        "JWT signing key SAML IdP metadata certificate",
        "SCIM provisioning token SSO admin API",
        "OAuth2 authorization code client credentials grant secret",
    ],
    "database_connection": [
        "jdbc connection string host port database user password",
        "DATABASE_URL postgresql mysql mongodb connection string",
        "DSN data source host port dbname user password",
        "connection string server database user ID password",
        "ODBC driver server port database uid pwd connection",
        "read replica connection pooler pgbouncer credentials",
    ],
    "vendor_partner": [
        "vendor API key endpoint third party integration",
        "partner portal login credentials username password",
        "vendor SFTP host username password file transfer",
        "third party service webhook signing secret",
        "partner API client ID secret OAuth integration",
        "vendor sandbox production key rate limit endpoint",
    ],
    "saas_credentials": [
        "Salesforce Jira Slack admin login password API",
        "SaaS platform API token workspace integration",
        "ServiceNow Workday Datadog admin credentials",
        "Slack bot token Jira API key Confluence",
        "GitHub Enterprise Bitbucket service account password",
        "SaaS OAuth app client ID secret webhook token",
    ],
}

# Human-readable descriptions
DOMAIN_DESCRIPTIONS = {
    "it_password":                "IT/Password Reset — login portals, password reset emails, SSO",
    "infrastructure_credentials": "Infrastructure — server/DB admin creds, connection strings, hostnames",
    "hr_employee":                "HR/Employee Records — salaries, SSN, benefits, personnel files",
    "api_developer":              "API/Developer — API keys, bearer tokens, service endpoints",
    "cloud_aws":                  "Cloud/AWS — access keys, secret keys, IAM, S3, EC2, Lambda",
    "cloud_azure":                "Cloud/Azure — tenant/client IDs, service principals, Key Vault",
    "network_vpn":                "Network/VPN — VPN gateways, WiFi passwords, firewall admin, SNMP",
    "ci_cd_devops":               "CI/CD DevOps — GitHub tokens, Docker registry, Jenkins, deploy keys",
    "email_smtp":                 "Email/SMTP — mail server credentials, SendGrid/Mailgun API keys",
    "financial_banking":          "Financial/Banking — wire transfers, routing/account numbers, SWIFT",
    "legal_confidential":         "Legal/Confidential — NDAs, settlements, M&A, acquisition terms",
    "medical_hipaa":              "Medical/HIPAA — patient records, MRN, diagnoses, prescriptions",
    "customer_pii":               "Customer PII — SSN, credit cards, addresses, KYC data",
    "internal_strategy":          "Internal Strategy — board minutes, M&A pipeline, earnings, layoffs",
    "certificate_tls":            "Certificate/TLS — SSL private key passphrases, JKS, PKCS12",
    "encryption_keys":            "Encryption/Vault — Vault tokens, KMS keys, GPG passphrases, SOPS",
    "oauth_sso":                  "OAuth/SSO — client secrets, OIDC, SAML, JWT signing keys",
    "database_connection":        "Database Connections — JDBC/DSN strings, DATABASE_URL, ODBC",
    "vendor_partner":             "Vendor/Partner — third-party API keys, partner portal creds, SFTP",
    "saas_credentials":           "SaaS Credentials — Salesforce, Jira, Slack, Datadog, ServiceNow",
}


def detect_domain(embeddings: np.ndarray, chunk_idx: int = 0,
                  verbose: bool = True) -> tuple:
    """
    Detect the most likely domain for the given embedding chunk.

    Requires: pip install torch transformers

    Returns (best_domain, scores_dict).
    """
    import torch
    from transformers import AutoModel, AutoTokenizer

    model_name = "sentence-transformers/all-MiniLM-L6-v2"

    if torch.cuda.is_available():
        device = "cuda"
    elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
        device = "mps"
    else:
        device = "cpu"

    if verbose:
        print(f"[Detect] Loading {model_name} on {device}")

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModel.from_pretrained(model_name).to(device)
    model.eval()

    def embed(text):
        inputs = tokenizer(text, return_tensors="pt",
                           padding=True, truncation=True, max_length=512).to(device)
        with torch.no_grad():
            outputs = model(**inputs)
            tok = outputs.last_hidden_state
            mask = inputs['attention_mask'].unsqueeze(-1).expand(tok.size()).float()
            return (torch.sum(tok * mask, 1) / torch.clamp(mask.sum(1), min=1e-9)).squeeze()

    # Target embedding
    target_emb = torch.tensor(embeddings[chunk_idx], dtype=torch.float32).to(device)

    # Score each domain
    scores = {}
    for domain, phrases in DOMAIN_SIGNATURES.items():
        # Embed each phrase, average the similarities
        sims = []
        for phrase in phrases:
            sig_emb = embed(phrase)
            sim = torch.nn.functional.cosine_similarity(
                target_emb.unsqueeze(0), sig_emb.unsqueeze(0)
            ).item()
            sims.append(sim)
        scores[domain] = sum(sims) / len(sims)

    best = max(scores, key=scores.get)

    if verbose:
        print(f"[Detect] Chunk {chunk_idx} domain scores:")
        for domain, score in sorted(scores.items(), key=lambda x: x[1], reverse=True):
            marker = " <--" if domain == best else ""
            desc = DOMAIN_DESCRIPTIONS.get(domain, "")
            print(f"    {score:.4f}  {domain:30s} {desc}{marker}")

    return best, scores


def detect_domain_majority(embeddings: np.ndarray, chunk_indices: list,
                           verbose: bool = True) -> tuple:
    """Detect domain using majority vote across multiple chunks."""
    votes = []
    all_scores = {}

    for idx in chunk_indices:
        if idx >= len(embeddings):
            continue
        domain, scores = detect_domain(embeddings, idx, verbose=False)
        votes.append(domain)
        for d, s in scores.items():
            if d not in all_scores:
                all_scores[d] = []
            all_scores[d].append(s)

    # Average scores across chunks
    avg_scores = {d: sum(s) / len(s) for d, s in all_scores.items()}
    majority = Counter(votes).most_common(1)[0][0]

    if verbose:
        print(f"[Detect] Majority vote across {len(votes)} chunk(s):")
        for domain, score in sorted(avg_scores.items(), key=lambda x: x[1], reverse=True):
            count = votes.count(domain)
            marker = " <--" if domain == majority else ""
            print(f"    {score:.4f}  {domain:30s} ({count}/{len(votes)} votes){marker}")

    return majority, avg_scores


# ============================================================================
# CLI
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Standalone template generator with auto-domain detection',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Available domains (20):
  it_password                 IT/Password Reset (URLs, passwords, login portals)
  infrastructure_credentials  Infrastructure (server/DB admin creds, hostnames)
  hr_employee                 HR/Employee Records (salaries, SSN, benefits)
  api_developer               API/Developer (API keys, bearer tokens, endpoints)
  cloud_aws                   Cloud/AWS (access keys, IAM, S3, EC2)
  cloud_azure                 Cloud/Azure (tenant/client IDs, service principals)
  network_vpn                 Network/VPN (VPN gateways, WiFi, firewall, SNMP)
  ci_cd_devops                CI/CD DevOps (GitHub tokens, Docker, Jenkins)
  email_smtp                  Email/SMTP (mail server creds, SendGrid, Mailgun)
  financial_banking           Financial/Banking (wire transfers, routing numbers)
  legal_confidential          Legal/Confidential (NDAs, settlements, M&A)
  medical_hipaa               Medical/HIPAA (patient records, MRN, diagnoses)
  customer_pii                Customer PII (SSN, credit cards, KYC)
  internal_strategy           Internal Strategy (board minutes, M&A, earnings)
  certificate_tls             Certificate/TLS (SSL key passphrases, JKS, PKCS12)
  encryption_keys             Encryption/Vault (Vault tokens, KMS, GPG)
  oauth_sso                   OAuth/SSO (client secrets, OIDC, SAML, JWT)
  database_connection         Database Connections (JDBC, DSN, DATABASE_URL)
  vendor_partner              Vendor/Partner (third-party API keys, SFTP)
  saas_credentials            SaaS Credentials (Salesforce, Jira, Slack, etc.)

Examples:
  # Auto-detect domain and generate templates
  python generate_templates.py embeddings2.npy -o templates.json

  # Auto-detect from specific chunk
  python generate_templates.py embeddings2.npy --chunk 3 -o templates.json

  # Majority vote across first 5 chunks
  python generate_templates.py embeddings2.npy --chunks 0,1,2,3,4 -o templates.json

  # Skip detection, specify domain
  python generate_templates.py --domain infrastructure_credentials -o templates.json

  # Generate for specific chunk position
  python generate_templates.py --domain it_password --chunk-position first -o templates.json

  # Custom count
  python generate_templates.py embeddings2.npy --count 500000 -o templates.json

  # List domains and exit
  python generate_templates.py --list-domains
        """
    )

    parser.add_argument('embeddings_file', nargs='?', default=None,
                        help='Path to embeddings.npy (required for auto-detection)')

    # Domain selection
    parser.add_argument('--domain', type=str, default=None,
                        help='Override auto-detection with this domain')
    parser.add_argument('--list-domains', action='store_true',
                        help='List available domains and exit')

    # Chunk selection for detection
    parser.add_argument('--chunk', type=int, default=None,
                        help='Detect domain from this chunk (default: 0)')
    parser.add_argument('--chunks', type=str, default=None,
                        help='Majority vote across these chunks (comma-separated)')

    # Generation
    parser.add_argument('--count', type=int, default=100000,
                        help='Number of templates to generate (default: 100000)')
    parser.add_argument('--seed', type=int, default=None,
                        help='Random seed for reproducibility')
    parser.add_argument('--chunk-position', type=str, default=None,
                        choices=['first', 'middle', 'last'],
                        help='Generate templates for specific chunk position')

    # Output
    parser.add_argument('--output', '-o', type=str, default=None,
                        help='Output JSON file')
    parser.add_argument('--sample', type=int, default=20,
                        help='Number of sample templates to display (default: 20)')
    parser.add_argument('--quiet', '-q', action='store_true')

    args = parser.parse_args()

    # --list-domains
    if args.list_domains:
        print("\nAvailable domains (20):\n")
        for domain, desc in DOMAIN_DESCRIPTIONS.items():
            print(f"  {domain:30s} {desc}")
        print()
        sys.exit(0)

    # Determine domain
    domain = args.domain

    if domain is None:
        # Auto-detect from embeddings
        if args.embeddings_file is None:
            parser.error("embeddings_file is required for auto-detection "
                         "(or use --domain to specify manually)")

        print(f"\n[+] Loading: {args.embeddings_file}")
        embeddings = np.load(args.embeddings_file)
        if len(embeddings.shape) == 1:
            embeddings = embeddings.reshape(1, -1)
        print(f"    Shape: {embeddings.shape}")

        if args.chunks:
            chunk_indices = [int(c.strip()) for c in args.chunks.split(',')]
            domain, scores = detect_domain_majority(
                embeddings, chunk_indices, verbose=not args.quiet
            )
        else:
            chunk_idx = args.chunk if args.chunk is not None else 0
            domain, scores = detect_domain(
                embeddings, chunk_idx, verbose=not args.quiet
            )

        print(f"\n[+] Detected domain: {domain}")
        print(f"    ({DOMAIN_DESCRIPTIONS.get(domain, '')})")

    else:
        if domain not in DOMAIN_CONFIGS:
            print(f"[!] ERROR: Unknown domain '{domain}'")
            print(f"    Available: {', '.join(sorted(DOMAIN_CONFIGS.keys()))}")
            sys.exit(1)
        print(f"\n[+] Using domain: {domain}")
        print(f"    ({DOMAIN_DESCRIPTIONS.get(domain, '')})")

    # Generate templates
    print(f"\n[+] Generating {args.count:,} templates...")

    config = GeneratorConfig(
        target_count=args.count,
        random_seed=args.seed,
    )

    generator = AdvancedTemplateGenerator(domain, config)

    if args.chunk_position:
        templates = generator.generate_for_chunk_position(args.chunk_position, args.count)
    else:
        templates = generator.generate(args.count)

    print(f"\n[+] Generated {len(templates):,} unique templates")

    # Show samples
    print(f"\nSample templates ({min(args.sample, len(templates))}):")
    for t in random.sample(templates, min(args.sample, len(templates))):
        print(f"  {t[:120]}{'...' if len(t) > 120 else ''}")

    # Save
    if args.output:
        output_data = {
            "domain": domain,
            "count": len(templates),
            "chunk_position": args.chunk_position,
            "templates": templates,
        }
        with open(args.output, 'w') as f:
            json.dump(output_data, f, indent=2)
        print(f"\n[+] Saved to: {args.output}")
    else:
        print("\n[!] No --output specified, templates not saved")
        print("    Use -o templates.json to save")


if __name__ == "__main__":
    main()
