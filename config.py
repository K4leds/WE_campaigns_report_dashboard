"""
Centralized configuration for WE Campaigns Report Dashboard
"""

# Channel cost per send (SAR) — only paid channels. Free channels (Push, In-App,
# On-Site, etc.) are handled implicitly: clean_data() falls back to 0.0 via .get().
CHANNEL_COSTS = {
    'Email': 0.0012,    # SAR per email
    'SMS': 0.0432,      # SAR per SMS
    'WhatsApp': 0.20,   # SAR per WhatsApp message
}

# Minimum columns required in uploaded CSV for the dashboard to work
REQUIRED_COLUMNS = ['Day', 'Campaign Name', 'Channel', 'Sent', 'Delivered']

# Chart theme & colors - Professional color palette for client-ready charts
COLORS = {
    'primary': '#0EA5E9',      # Sky Blue
    'secondary': '#7C3AED',    # Purple
    'success': '#22C55E',      # Green
    'warning': '#F59E0B',      # Amber
    'danger': '#EF4444',       # Red
    'info': '#6366F1',         # Indigo
    'muted': '#6B7280',        # Gray
}

# Full design tokens for themes (matches .streamlit/config.toml)
PALETTE = {
    'dark': {
        'background': '#0F172A',          # slate-900
        'surface': '#1E293B',             # slate-800
        'text': '#F1F5F9',                # slate-100
        'text_muted': '#94A3B8',          # slate-400
        'border': '#334155',              # slate-700
        'primary': '#0EA5E9',
        'success': '#22C55E',
        'warning': '#F59E0B',
        'danger': '#EF4444',
        'info': '#6366F1',
    },
    'light': {
        'background': '#F8FAFC',          # slate-50
        'surface': '#FFFFFF',
        'text': '#0F172A',                # slate-900
        'text_muted': '#64748B',          # slate-500
        'border': '#E2E8F0',              # slate-200
        'primary': '#0EA5E9',
        'success': '#22C55E',
        'warning': '#F59E0B',
        'danger': '#EF4444',
        'info': '#6366F1',
    },
}

# Ordered sequence for multi-series charts
COLOR_SEQUENCE = ['#2563EB', '#059669', '#D97706', '#DC2626', '#7C3AED', '#0891B2',
                  '#4F46E5', '#0D9488', '#EA580C', '#E11D48', '#9333EA', '#0284C7']

# Channel-specific colors for consistent channel identity across all charts
CHANNEL_COLORS = {
    'Email': '#2563EB',
    'SMS': '#7C3AED',
    'WhatsApp': '#059669',
    'Push': '#D97706',
    'Mobile Push': '#EA580C',
    'App Push': '#EA580C',
    'Web Push': '#0891B2',
    'In-App': '#4F46E5',
    'On-Site': '#0D9488',
    'Web Personalization (Inline content)': '#6366F1',
}

# Attribution model labels for display
REVENUE_ATTRIBUTION_LABELS = {
    "Total": "Revenue (SAR)",
    "Click-Through": "Click-Through Revenue (SAR)",
    "Impression-Through": "Impression-Through Revenue (SAR)"
}

CONVERSION_ATTRIBUTION_LABELS = {
    "Total": "Unique Conversions",
    "Click-Through": "Click-Through Conversions",
    "Impression-Through": "Impression-Through Conversions"
}
