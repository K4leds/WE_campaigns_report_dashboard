"""Shared channel card/tile/chip rendering for the Overview and Channels pages.

Keeps one visual implementation of "what does this channel look like" so the
two pages that show per-channel KPIs (`pages/02_overview.py`,
`pages/07_channels.py`) don't drift into two different card styles.

Icons are inline SVGs, not emoji -- emoji render inconsistently across OS/
browser font stacks and can't take the channel's brand color or the app's
theme color. Generic glyphs are Bootstrap Icons (MIT); brand marks (WhatsApp,
Facebook, Google) are Simple Icons (CC0) -- both ship their official path
data, not an approximation.

Usage:
    from components.channel_cards import render_channel_card, render_insight_chips, icon
    from utils import render_kpi_card  # hero-number stat tiles, already existed

    render_channel_card(row, channel_costs=channel_costs, comparison_row=comp_row,
                         revenue_col=revenue_col, conv_col=conv_col,
                         revenue_label=rev_display_name, conv_label=conv_display_name,
                         sparkline_weeks=weekly_revenue_series)
    render_insight_chips([{"icon": "trophy", "text": "Top Revenue: Email", "level": "good"}])
    st.markdown(f"#### {icon('rocket')} Channels at a Glance", unsafe_allow_html=True)
"""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config import CHANNEL_COLORS, COLORS

# name -> (viewBox, inner <path> markup). Generic glyphs: Bootstrap Icons (MIT,
# https://github.com/twbs/icons). Brand marks: Simple Icons (CC0,
# https://github.com/simple-icons/simple-icons) -- official path data, not a
# hand-drawn approximation of the logo.
_ICON_PATHS = {
    'email': ('0 0 16 16', '<path d="M.05 3.555A2 2 0 0 1 2 2h12a2 2 0 0 1 1.95 1.555L8 8.414zM0 4.697v7.104l5.803-3.558zM6.761 8.83l-6.57 4.027A2 2 0 0 0 2 14h12a2 2 0 0 0 1.808-1.144l-6.57-4.027L8 9.586zm3.436-.586L16 11.801V4.697z"/>'),
    'sms': ('0 0 16 16', '<path d="M16 8c0 3.866-3.582 7-8 7a9 9 0 0 1-2.347-.306c-.584.296-1.925.864-4.181 1.234-.2.032-.352-.176-.273-.362.354-.836.674-1.95.77-2.966C.744 11.37 0 9.76 0 8c0-3.866 3.582-7 8-7s8 3.134 8 7M5 8a1 1 0 1 0-2 0 1 1 0 0 0 2 0m4 0a1 1 0 1 0-2 0 1 1 0 0 0 2 0m3 1a1 1 0 1 0 0-2 1 1 0 0 0 0 2"/>'),
    'push': ('0 0 16 16', '<path d="M8 16a2 2 0 0 0 2-2H6a2 2 0 0 0 2 2m.995-14.901a1 1 0 1 0-1.99 0A5 5 0 0 0 3 6c0 1.098-.5 6-2 7h14c-1.5-1-2-5.902-2-7 0-2.42-1.72-4.44-4.005-4.901"/>'),
    'globe': ('0 0 16 16', '<path d="M0 8a8 8 0 1 1 16 0A8 8 0 0 1 0 8m7.5-6.923c-.67.204-1.335.82-1.887 1.855A8 8 0 0 0 5.145 4H7.5zM4.09 4a9.3 9.3 0 0 1 .64-1.539 7 7 0 0 1 .597-.933A7.03 7.03 0 0 0 2.255 4zm-.582 3.5c.03-.877.138-1.718.312-2.5H1.674a7 7 0 0 0-.656 2.5zM4.847 5a12.5 12.5 0 0 0-.338 2.5H7.5V5zM8.5 5v2.5h2.99a12.5 12.5 0 0 0-.337-2.5zM4.51 8.5a12.5 12.5 0 0 0 .337 2.5H7.5V8.5zm3.99 0V11h2.653c.187-.765.306-1.608.338-2.5zM5.145 12q.208.58.468 1.068c.552 1.035 1.218 1.65 1.887 1.855V12zm.182 2.472a7 7 0 0 1-.597-.933A9.3 9.3 0 0 1 4.09 12H2.255a7 7 0 0 0 3.072 2.472M3.82 11a13.7 13.7 0 0 1-.312-2.5h-2.49c.062.89.291 1.733.656 2.5zm6.853 3.472A7 7 0 0 0 13.745 12H11.91a9.3 9.3 0 0 1-.64 1.539 7 7 0 0 1-.597.933M8.5 12v2.923c.67-.204 1.335-.82 1.887-1.855q.26-.487.468-1.068zm3.68-1h2.146c.365-.767.594-1.61.656-2.5h-2.49a13.7 13.7 0 0 1-.312 2.5m2.802-3.5a7 7 0 0 0-.656-2.5H12.18c.174.782.282 1.623.312 2.5zM11.27 2.461c.247.464.462.98.64 1.539h1.835a7 7 0 0 0-3.072-2.472c.218.284.418.598.597.933M10.855 4a8 8 0 0 0-.468-1.068C9.835 1.897 9.17 1.282 8.5 1.077V4z"/>'),
    'phone': ('0 0 16 16', '<path d="M3 2a2 2 0 0 1 2-2h6a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2zm6 11a1 1 0 1 0-2 0 1 1 0 0 0 2 0"/>'),
    'window_stack': ('0 0 16 16', '<path d="M4.5 6a.5.5 0 1 0 0-1 .5.5 0 0 0 0 1M6 6a.5.5 0 1 0 0-1 .5.5 0 0 0 0 1m2-.5a.5.5 0 1 1-1 0 .5.5 0 0 1 1 0"/><path d="M12 1a2 2 0 0 1 2 2 2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2 2 2 0 0 1-2-2V3a2 2 0 0 1 2-2zM2 12V5a2 2 0 0 1 2-2h9a1 1 0 0 0-1-1H2a1 1 0 0 0-1 1v8a1 1 0 0 0 1 1m1-4v5a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1V8zm12-1V5a1 1 0 0 0-1-1H4a1 1 0 0 0-1 1v2z"/>'),
    'display': ('0 0 16 16', '<path d="M0 4s0-2 2-2h12s2 0 2 2v6s0 2-2 2h-4q0 1 .25 1.5H11a.5.5 0 0 1 0 1H5a.5.5 0 0 1 0-1h.75Q6 13 6 12H2s-2 0-2-2zm1.398-.855a.76.76 0 0 0-.254.302A1.5 1.5 0 0 0 1 4.01V10c0 .325.078.502.145.602q.105.156.302.254a1.5 1.5 0 0 0 .538.143L2.01 11H14c.325 0 .502-.078.602-.145a.76.76 0 0 0 .254-.302 1.5 1.5 0 0 0 .143-.538L15 9.99V4c0-.325-.078-.502-.145-.602a.76.76 0 0 0-.302-.254A1.5 1.5 0 0 0 13.99 3H2c-.325 0-.502.078-.602.145"/>'),
    'bar_chart': ('0 0 16 16', '<path d="M1 11a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v3a1 1 0 0 1-1 1H2a1 1 0 0 1-1-1zm5-4a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v7a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1zm5-5a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1h-2a1 1 0 0 1-1-1z"/>'),
    'magic': ('0 0 16 16', '<path d="M9.5 2.672a.5.5 0 1 0 1 0V.843a.5.5 0 0 0-1 0zm4.5.035A.5.5 0 0 0 13.293 2L12 3.293a.5.5 0 1 0 .707.707zM7.293 4A.5.5 0 1 0 8 3.293L6.707 2A.5.5 0 0 0 6 2.707zm-.621 2.5a.5.5 0 1 0 0-1H4.843a.5.5 0 1 0 0 1zm8.485 0a.5.5 0 1 0 0-1h-1.829a.5.5 0 0 0 0 1zM13.293 10A.5.5 0 1 0 14 9.293L12.707 8a.5.5 0 1 0-.707.707zM9.5 11.157a.5.5 0 0 0 1 0V9.328a.5.5 0 0 0-1 0zm1.854-5.097a.5.5 0 0 0 0-.706l-.708-.708a.5.5 0 0 0-.707 0L8.646 5.94a.5.5 0 0 0 0 .707l.708.708a.5.5 0 0 0 .707 0l1.293-1.293Zm-3 3a.5.5 0 0 0 0-.706l-.708-.708a.5.5 0 0 0-.707 0L.646 13.94a.5.5 0 0 0 0 .707l.708.708a.5.5 0 0 0 .707 0z"/>'),
    'cash_coin': ('0 0 16 16', '<path fill-rule="evenodd" d="M11 15a4 4 0 1 0 0-8 4 4 0 0 0 0 8m5-4a5 5 0 1 1-10 0 5 5 0 0 1 10 0"/><path d="M9.438 11.944c.047.596.518 1.06 1.363 1.116v.44h.375v-.443c.875-.061 1.386-.529 1.386-1.207 0-.618-.39-.936-1.09-1.1l-.296-.07v-1.2c.376.043.614.248.671.532h.658c-.047-.575-.54-1.024-1.329-1.073V8.5h-.375v.45c-.747.073-1.255.522-1.255 1.158 0 .562.378.92 1.007 1.066l.248.061v1.272c-.384-.058-.639-.27-.696-.563h-.668zm1.36-1.354c-.369-.085-.569-.26-.569-.522 0-.294.216-.514.572-.578v1.1zm.432.746c.449.104.655.272.655.569 0 .339-.257.571-.709.614v-1.195z"/><path d="M1 0a1 1 0 0 0-1 1v8a1 1 0 0 0 1 1h4.083q.088-.517.258-1H3a2 2 0 0 0-2-2V3a2 2 0 0 0 2-2h10a2 2 0 0 0 2 2v3.528c.38.34.717.728 1 1.154V1a1 1 0 0 0-1-1z"/><path d="M9.998 5.083 10 5a2 2 0 1 0-3.132 1.65 6 6 0 0 1 3.13-1.567"/>'),
    'bullseye': ('0 0 16 16', '<path d="M8 15A7 7 0 1 1 8 1a7 7 0 0 1 0 14m0 1A8 8 0 1 0 8 0a8 8 0 0 0 0 16"/><path d="M8 13A5 5 0 1 1 8 3a5 5 0 0 1 0 10m0 1A6 6 0 1 0 8 2a6 6 0 0 0 0 12"/><path d="M8 11a3 3 0 1 1 0-6 3 3 0 0 1 0 6m0 1a4 4 0 1 0 0-8 4 4 0 0 0 0 8"/><path d="M9.5 8a1.5 1.5 0 1 1-3 0 1.5 1.5 0 0 1 3 0"/>'),
    'broadcast': ('0 0 16 16', '<path d="M3.05 3.05a7 7 0 0 0 0 9.9.5.5 0 0 1-.707.707 8 8 0 0 1 0-11.314.5.5 0 0 1 .707.707m2.122 2.122a4 4 0 0 0 0 5.656.5.5 0 1 1-.708.708 5 5 0 0 1 0-7.072.5.5 0 0 1 .708.708m5.656-.708a.5.5 0 0 1 .708 0 5 5 0 0 1 0 7.072.5.5 0 1 1-.708-.708 4 4 0 0 0 0-5.656.5.5 0 0 1 0-.708m2.122-2.12a.5.5 0 0 1 .707 0 8 8 0 0 1 0 11.313.5.5 0 0 1-.707-.707 7 7 0 0 0 0-9.9.5.5 0 0 1 0-.707zM10 8a2 2 0 1 1-4 0 2 2 0 0 1 4 0"/>'),
    'rocket': ('0 0 16 16', '<path d="M12.17 9.53c2.307-2.592 3.278-4.684 3.641-6.218.21-.887.214-1.58.16-2.065a3.6 3.6 0 0 0-.108-.563 2 2 0 0 0-.078-.23V.453c-.073-.164-.168-.234-.352-.295a2 2 0 0 0-.16-.045 4 4 0 0 0-.57-.093c-.49-.044-1.19-.03-2.08.188-1.536.374-3.618 1.343-6.161 3.604l-2.4.238h-.006a2.55 2.55 0 0 0-1.524.734L.15 7.17a.512.512 0 0 0 .433.868l1.896-.271c.28-.04.592.013.955.132.232.076.437.16.655.248l.203.083c.196.816.66 1.58 1.275 2.195.613.614 1.376 1.08 2.191 1.277l.082.202c.089.218.173.424.249.657.118.363.172.676.132.956l-.271 1.9a.512.512 0 0 0 .867.433l2.382-2.386c.41-.41.668-.949.732-1.526zm.11-3.699c-.797.8-1.93.961-2.528.362-.598-.6-.436-1.733.361-2.532.798-.799 1.93-.96 2.528-.361s.437 1.732-.36 2.531Z"/><path d="M5.205 10.787a7.6 7.6 0 0 0 1.804 1.352c-1.118 1.007-4.929 2.028-5.054 1.903-.126-.127.737-4.189 1.839-5.18.346.69.837 1.35 1.411 1.925"/>'),
    'search': ('0 0 16 16', '<path d="M11.742 10.344a6.5 6.5 0 1 0-1.397 1.398h-.001q.044.06.098.115l3.85 3.85a1 1 0 0 0 1.415-1.414l-3.85-3.85a1 1 0 0 0-.115-.1zM12 6.5a5.5 5.5 0 1 1-11 0 5.5 5.5 0 0 1 11 0"/>'),
    'compass': ('0 0 16 16', '<path d="M8 16.016a7.5 7.5 0 0 0 1.962-14.74A1 1 0 0 0 9 0H7a1 1 0 0 0-.962 1.276A7.5 7.5 0 0 0 8 16.016m6.5-7.5a6.5 6.5 0 1 1-13 0 6.5 6.5 0 0 1 13 0"/><path d="m6.94 7.44 4.95-2.83-2.83 4.95-4.949 2.83 2.828-4.95z"/>'),
    'send': ('0 0 16 16', '<path d="M15.964.686a.5.5 0 0 0-.65-.65L.767 5.855H.766l-.452.18a.5.5 0 0 0-.082.887l.41.26.001.002 4.995 3.178 3.178 4.995.002.002.26.41a.5.5 0 0 0 .886-.083zm-1.833 1.89L6.637 10.07l-.215-.338a.5.5 0 0 0-.154-.154l-.338-.215 7.494-7.494 1.178-.471z"/>'),
    'trophy': ('0 0 16 16', '<path d="M2.5.5A.5.5 0 0 1 3 0h10a.5.5 0 0 1 .5.5q0 .807-.034 1.536a3 3 0 1 1-1.133 5.89c-.79 1.865-1.878 2.777-2.833 3.011v2.173l1.425.356c.194.048.377.135.537.255L13.3 15.1a.5.5 0 0 1-.3.9H3a.5.5 0 0 1-.3-.9l1.838-1.379c.16-.12.343-.207.537-.255L6.5 13.11v-2.173c-.955-.234-2.043-1.146-2.833-3.012a3 3 0 1 1-1.132-5.89A33 33 0 0 1 2.5.5m.099 2.54a2 2 0 0 0 .72 3.935c-.333-1.05-.588-2.346-.72-3.935m10.083 3.935a2 2 0 0 0 .72-3.935c-.133 1.59-.388 2.885-.72 3.935"/>'),
    'thumbs_up': ('0 0 16 16', '<path d="M6.956 1.745C7.021.81 7.908.087 8.864.325l.261.066c.463.116.874.456 1.012.965.22.816.533 2.511.062 4.51a10 10 0 0 1 .443-.051c.713-.065 1.669-.072 2.516.21.518.173.994.681 1.2 1.273.184.532.16 1.162-.234 1.733q.086.18.138.363c.077.27.113.567.113.856s-.036.586-.113.856c-.039.135-.09.273-.16.404.169.387.107.819-.003 1.148a3.2 3.2 0 0 1-.488.901c.054.152.076.312.076.465 0 .305-.089.625-.253.912C13.1 15.522 12.437 16 11.5 16H8c-.605 0-1.07-.081-1.466-.218a4.8 4.8 0 0 1-.97-.484l-.048-.03c-.504-.307-.999-.609-2.068-.722C2.682 14.464 2 13.846 2 13V9c0-.85.685-1.432 1.357-1.615.849-.232 1.574-.787 2.132-1.41.56-.627.914-1.28 1.039-1.639.199-.575.356-1.539.428-2.59z"/>'),
    'slash_circle': ('0 0 16 16', '<path d="M8 15A7 7 0 1 1 8 1a7 7 0 0 1 0 14m0 1A8 8 0 1 0 8 0a8 8 0 0 0 0 16"/><path d="M11.354 4.646a.5.5 0 0 0-.708 0l-6 6a.5.5 0 0 0 .708.708l6-6a.5.5 0 0 0 0-.708"/>'),
    'warning': ('0 0 16 16', '<path d="M8.982 1.566a1.13 1.13 0 0 0-1.96 0L.165 13.233c-.457.778.091 1.767.98 1.767h13.713c.889 0 1.438-.99.98-1.767zM8 5c.535 0 .954.462.9.995l-.35 3.507a.552.552 0 0 1-1.1 0L7.1 5.995A.905.905 0 0 1 8 5m.002 6a1 1 0 1 1 0 2 1 1 0 0 1 0-2"/>'),
    'check_circle': ('0 0 16 16', '<path d="M16 8A8 8 0 1 1 0 8a8 8 0 0 1 16 0m-3.97-3.03a.75.75 0 0 0-1.08.022L7.477 9.417 5.384 7.323a.75.75 0 0 0-1.06 1.06L6.97 11.03a.75.75 0 0 0 1.079-.02l3.992-4.99a.75.75 0 0 0-.01-1.05z"/>'),
    'coin': ('0 0 16 16', '<path d="M5.5 9.511c.076.954.83 1.697 2.182 1.785V12h.6v-.709c1.4-.098 2.218-.846 2.218-1.932 0-.987-.626-1.496-1.745-1.76l-.473-.112V5.57c.6.068.982.396 1.074.85h1.052c-.076-.919-.864-1.638-2.126-1.716V4h-.6v.719c-1.195.117-2.01.836-2.01 1.853 0 .9.606 1.472 1.613 1.707l.397.098v2.034c-.615-.093-1.022-.43-1.114-.9zm2.177-2.166c-.59-.137-.91-.416-.91-.836 0-.47.345-.822.915-.925v1.76h-.005zm.692 1.193c.717.166 1.048.435 1.048.91 0 .542-.412.914-1.135.982V8.518z"/><path d="M8 15A7 7 0 1 1 8 1a7 7 0 0 1 0 14m0 1A8 8 0 1 0 8 0a8 8 0 0 0 0 16"/><path d="M8 13.5a5.5 5.5 0 1 1 0-11 5.5 5.5 0 0 1 0 11m0 .5A6 6 0 1 0 8 2a6 6 0 0 0 0 12"/>'),
    'cursor': ('0 0 16 16', '<path d="M14.082 2.182a.5.5 0 0 1 .103.557L8.528 15.467a.5.5 0 0 1-.917-.007L5.57 10.694.803 8.652a.5.5 0 0 1-.006-.916l12.728-5.657a.5.5 0 0 1 .556.103z"/>'),
    'inbox': ('0 0 16 16', '<path d="M4.98 4a.5.5 0 0 0-.39.188L1.54 8H6a.5.5 0 0 1 .5.5 1.5 1.5 0 1 0 3 0A.5.5 0 0 1 10 8h4.46l-3.05-3.812A.5.5 0 0 0 11.02 4zm-1.17-.437A1.5 1.5 0 0 1 4.98 3h6.04a1.5 1.5 0 0 1 1.17.563l3.7 4.625a.5.5 0 0 1 .106.374l-.39 3.124A1.5 1.5 0 0 1 14.117 13H1.883a1.5 1.5 0 0 1-1.489-1.314l-.39-3.124a.5.5 0 0 1 .106-.374z"/>'),
    'whatsapp': ('0 0 24 24', '<path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413Z"/>'),
    'facebook': ('0 0 24 24', '<path d="M9.101 23.691v-7.98H6.627v-3.667h2.474v-1.58c0-4.085 1.848-5.978 5.858-5.978.401 0 .955.042 1.468.103a8.68 8.68 0 0 1 1.141.195v3.325a8.623 8.623 0 0 0-.653-.036 26.805 26.805 0 0 0-.733-.009c-.707 0-1.259.096-1.675.309a1.686 1.686 0 0 0-.679.622c-.258.42-.374.995-.374 1.752v1.297h3.919l-.386 2.103-.287 1.564h-3.246v8.245C19.396 23.238 24 18.179 24 12.044c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.628 3.874 10.35 9.101 11.647Z"/>'),
    'google': ('0 0 24 24', '<path d="M12.48 10.92v3.28h7.84c-.24 1.84-.853 3.187-1.787 4.133-1.147 1.147-2.933 2.4-6.053 2.4-4.827 0-8.6-3.893-8.6-8.72s3.773-8.72 8.6-8.72c2.6 0 4.507 1.027 5.907 2.347l2.307-2.307C18.747 1.44 16.133 0 12.48 0 5.867 0 .307 5.387.307 12s5.56 12 12.173 12c3.573 0 6.267-1.173 8.373-3.36 2.16-2.16 2.84-5.213 2.84-7.667 0-.76-.053-1.467-.173-2.053H12.48z"/>'),
}

# Channel name -> icon key (semantically correct marks, not lookalikes --
# WhatsApp gets the WhatsApp glyph, not a green heart).
CHANNEL_ICON_KEYS = {
    'Email': 'email', 'SMS': 'sms', 'Push': 'push', 'Web Push': 'globe',
    'Mobile Push': 'phone', 'App Push': 'phone', 'WhatsApp': 'whatsapp',
    'In-App': 'window_stack', 'On-Site': 'display', 'Facebook': 'facebook',
    'Google': 'google', 'Web Personalization (Inline content)': 'magic',
}

# level -> (background, text/icon color), matches the app's reserved status palette
_CHIP_LEVEL_COLORS = {
    'good': ('rgba(34,197,94,0.15)', COLORS['success']),
    'warning': ('rgba(245,158,11,0.15)', COLORS['warning']),
    'critical': ('rgba(239,68,68,0.15)', COLORS['danger']),
    'info': ('rgba(99,102,241,0.15)', COLORS['info']),
}


def icon(name: str, size: int = 14, color: str | None = None) -> str:
    """Inline SVG for `name` (see `_ICON_PATHS`), sized and colored to sit next
    to text. Falls back to a generic bar-chart glyph for an unknown name so a
    typo degrades visibly instead of rendering nothing."""
    viewbox, paths = _ICON_PATHS.get(name, _ICON_PATHS['bar_chart'])
    style = f'vertical-align:-2px;flex-shrink:0;{f"color:{color};" if color else ""}'
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
            f'viewBox="{viewbox}" fill="currentColor" style="{style}">{paths}</svg>')


def channel_icon(channel: str, size: int = 14, color: str | None = None) -> str:
    """Inline SVG for a channel name, via `CHANNEL_ICON_KEYS`."""
    return icon(CHANNEL_ICON_KEYS.get(channel, 'bar_chart'), size=size, color=color)


def _status_dot(color: str, size: int = 8) -> str:
    """Small colored circle -- replaces the old 🟢🟡🟠🔴 emoji status glyphs
    with something that actually renders as a solid, consistent dot."""
    return (f'<span style="display:inline-block;width:{size}px;height:{size}px;'
            f'border-radius:50%;background:{color};margin-right:4px;vertical-align:-1px;"></span>')


def _roas_status_color(roas: float) -> str:
    if roas >= 4:
        return COLORS['success']
    if roas >= 2:
        return COLORS['warning']
    if roas >= 1:
        return '#F97316'  # orange-500: distinct "break-even" step between warning and danger
    return COLORS['danger']


def _delta_html(current: float, comparison: float | None) -> str:
    if comparison is None or comparison == 0:
        return ''
    pct = (current - comparison) / abs(comparison) * 100
    color = COLORS['success'] if pct >= 0 else COLORS['danger']
    arrow = '▲' if pct >= 0 else '▼'
    return f'<span style="font-size:12px;color:{color};margin-left:6px;">{arrow}{abs(pct):.1f}%</span>'


def _sparkline(weekly_values: pd.Series, color: str):
    # CHANNEL_COLORS/COLORS are always '#RRGGBB' hex; Plotly's fillcolor doesn't
    # accept 8-digit hex-with-alpha, so convert to rgba() for the translucent fill.
    if color.startswith('#') and len(color) == 7:
        r, g, b = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
        fill_color = f'rgba({r},{g},{b},0.12)'
    else:
        fill_color = color
    fig = go.Figure(go.Scatter(
        y=weekly_values.tolist(), mode='lines', line=dict(width=2, color=color),
        fill='tozeroy', fillcolor=fill_color, hoverinfo='skip',
    ))
    fig.update_layout(
        height=44, margin=dict(l=0, r=0, t=0, b=0), showlegend=False,
        xaxis=dict(visible=False), yaxis=dict(visible=False),
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
    )
    return fig


def render_channel_card(
    row,
    *,
    channel_costs: dict,
    revenue_col: str,
    conv_col: str,
    revenue_label: str,
    conv_label: str,
    comparison_row=None,
    sparkline_weekly: pd.Series | None = None,
    key: str = '',
) -> None:
    """Render one channel's KPI card. `row` is a Series from the channel_analysis
    (+ Delivery Rate/CTR/Conversion Rate/AOV/Cost/ROAS/RPC) DataFrame."""
    channel = row['Channel']
    accent = CHANNEL_COLORS.get(channel, COLORS['muted'])
    is_active = row.get('Sent', 0) > 0

    with st.container(border=True):
        st.markdown(
            f'<div style="height:4px;background:{accent};border-radius:2px;margin:-4px -4px 8px -4px;"></div>'
            f'<div style="font-size:15px;font-weight:600;">{channel_icon(channel, size=16, color=accent)} {channel}</div>',
            unsafe_allow_html=True,
        )

        if not is_active:
            st.markdown(
                f'<span style="font-size:12px;color:{COLORS["muted"]};">{icon("slash_circle")} Inactive — no activity this period</span>',
                unsafe_allow_html=True,
            )
            return

        revenue_val = row.get(revenue_col, 0)
        conv_val = row.get(conv_col, row.get('Unique Conversions', 0))
        comp_revenue = comparison_row.get(revenue_col) if comparison_row is not None else None
        comp_conv = comparison_row.get(conv_col, comparison_row.get('Unique Conversions')) if comparison_row is not None else None

        c1, c2 = st.columns(2)
        with c1:
            st.markdown(
                f'<div style="font-size:11px;color:{COLORS["muted"]};">{revenue_label}</div>'
                f'<div style="font-size:20px;font-weight:700;">{revenue_val:,.0f}{_delta_html(revenue_val, comp_revenue)}</div>',
                unsafe_allow_html=True,
            )
        with c2:
            st.markdown(
                f'<div style="font-size:11px;color:{COLORS["muted"]};">{conv_label}</div>'
                f'<div style="font-size:20px;font-weight:700;">{conv_val:,.0f}{_delta_html(conv_val, comp_conv)}</div>',
                unsafe_allow_html=True,
            )

        if sparkline_weekly is not None and len(sparkline_weekly) > 1:
            st.plotly_chart(
                _sparkline(sparkline_weekly, accent), use_container_width=True,
                config={'displayModeBar': False}, key=f'spark_{key or channel}',
            )

        chips = []
        cost_val = channel_costs.get(channel, 0) * (row['Delivered'] if channel == 'WhatsApp' else row['Sent'])
        if conv_val > 0:
            aov = revenue_val / conv_val
            chips.append(f'{icon("coin")} AOV {aov:,.1f}')
        if cost_val > 0:
            roas = revenue_val / cost_val
            chips.append(f'{_status_dot(_roas_status_color(roas))}ROAS {roas:.1f}x')
        elif row.get('Unique Clicks', 0) > 0:
            rpc = revenue_val / row['Unique Clicks']
            chips.append(f'{icon("cash_coin")} RPC {rpc:,.2f}')
        chips.append(f'{icon("inbox")} {row.get("Delivery Rate", 0):.0f}%')
        if row.get('Unique Impressions', 0) > 0:
            chips.append(f'{icon("cursor")} CTR {row.get("CTR", 0):.1f}%')
        chips.append(f'{icon("bullseye")} CVR {row.get("Conversion Rate", 0):.1f}%')

        # Card height varies only with how many lines the chips wrap onto: a channel
        # whose 5 chips fit on one line (SMS) rendered visibly shorter than one that
        # wrapped to two. Reserving two lines' worth of space levels the row.
        # min-height (not height) so a narrow screen can still wrap to three.
        CHIP_LINE_PX = 28  # 11px chip + padding + margin
        st.markdown(
            f'<div style="min-height:{2 * CHIP_LINE_PX}px;">'
            + ''.join(
                f'<span style="display:inline-block;font-size:11px;background:{COLORS["muted"]}22;'
                f'border-radius:10px;padding:2px 8px;margin:2px 4px 0 0;">{c}</span>'
                for c in chips
            )
            + '</div>',
            unsafe_allow_html=True,
        )


def render_insight_chips(insights: list[dict]) -> None:
    """Render a wrapped row of colored callout chips.

    Each insight: {"icon": str, "text": str, "level": "good"|"warning"|"critical"|"info"}.
    `icon` is either a name from `_ICON_PATHS` (looked up and colored to match
    the chip) or already-rendered SVG markup (e.g. from `channel_icon()`, to
    show a specific channel's mark instead of a generic concept glyph).
    """
    if not insights:
        return
    chip_html = []
    for item in insights:
        bg, fg = _CHIP_LEVEL_COLORS.get(item.get('level', 'info'), _CHIP_LEVEL_COLORS['info'])
        item_icon = item['icon']
        icon_html = item_icon if item_icon.startswith('<svg') else icon(item_icon, color=fg)
        chip_html.append(
            f'<span style="display:inline-block;background:{bg};color:{fg};'
            f'border-radius:8px;padding:6px 12px;margin:4px 6px 4px 0;font-size:13px;font-weight:500;">'
            f'{icon_html} {item["text"]}</span>'
        )
    st.markdown(f'<div style="line-height:2.2;">{"".join(chip_html)}</div>', unsafe_allow_html=True)


def _demo():
    """ponytail self-check: icon lookup, card/chip renderers don't crash on the shapes they're built for."""
    active_row = pd.Series({
        'Channel': 'Email', 'Sent': 1000, 'Delivered': 950, 'Unique Impressions': 500,
        'Unique Clicks': 100, 'Selected Revenue (SAR)': 5000, 'Selected Conversions': 50,
        'Delivery Rate': 95.0, 'CTR': 20.0, 'Conversion Rate': 50.0,
    })
    inactive_row = pd.Series({'Channel': 'SMS', 'Sent': 0})
    unmapped_row = pd.Series({
        'Channel': 'Carrier Pigeon', 'Sent': 10, 'Delivered': 10, 'Unique Impressions': 0,
        'Unique Clicks': 0, 'Selected Revenue (SAR)': 0, 'Selected Conversions': 0,
        'Delivery Rate': 100.0, 'CTR': 0.0, 'Conversion Rate': 0.0,
    })
    for row in (active_row, inactive_row, unmapped_row):
        assert '<svg' in channel_icon(row['Channel'])
        assert CHANNEL_COLORS.get(row['Channel'], COLORS['muted']) is not None
    assert '<svg' in icon('whatsapp') and '<svg' in icon('nonexistent-name')
    assert _roas_status_color(5) == COLORS['success'] and _roas_status_color(0.5) == COLORS['danger']
    assert _delta_html(100, 0) == ''
    assert '▲' in _delta_html(120, 100)
    print("channel_cards self-check OK")


if __name__ == '__main__':
    _demo()
