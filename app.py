"""SCR Research Lab — Streamlit MVP."""
import io
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
import yfinance as yf
from engine import Params, indicators, signals, run_backtest, resample_ohlc

st.set_page_config(page_title='SCR Research Lab', page_icon='📈', layout='wide')
st.title('📈 SCR Research Lab · 무료 백테스트')
st.caption('한국 · 미국 · 일본 | Stochastic + CCI + RSI | SCR 원문 예시 기반 신호 연구 v0.6')
st.warning('이 전략은 캡처에 있는 SCR 원문과 동일하다고 검증되지 않았습니다. 성과는 미래 수익을 보장하지 않습니다.', icon='⚠️')

EXAMPLES = {'🇺🇸 미국': {'SOXX': 'SOXX', 'TQQQ': 'TQQQ', 'SPY': 'SPY', 'NVDA': 'NVDA'},
            '🇰🇷 한국': {'삼성전자': '005930.KS', 'SK하이닉스': '000660.KS', 'NAVER': '035420.KS'},
            '🇯🇵 일본': {'도요타': '7203.T', '소니': '6758.T', '도쿄해상': '8766.T'}}

@st.cache_data(ttl=3600, show_spinner=False)
def load_prices(symbol: str, period: str) -> pd.DataFrame:
    raw = yf.Ticker(symbol).history(period=period, interval='1d', auto_adjust=True)
    if raw is None or raw.empty:
        raise ValueError('가격 데이터를 받지 못했습니다. 티커, 인터넷 연결, 데이터 공급원 상태를 확인하세요.')
    if raw.index.tz is not None:
        raw.index = raw.index.tz_localize(None)
    raw.index = pd.to_datetime(raw.index).normalize()
    raw = raw[['Open','High','Low','Close','Volume']].dropna(subset=['Open','High','Low','Close'])
    raw = raw[(raw[['Open','High','Low','Close']] > 0).all(axis=1)]
    if len(raw) < 30:
        raise ValueError('가용 데이터가 부족합니다.')
    return raw[~raw.index.duplicated(keep='last')].sort_index()

with st.sidebar:
    st.header('① 데이터')
    market = st.selectbox('시장', list(EXAMPLES))
    label = st.selectbox('대표 종목', list(EXAMPLES[market]))
    custom = st.text_input('직접 티커 입력 (우선 적용)', placeholder='예: 005930.KS, SOXX, 7203.T')
    ticker = custom.strip().upper() or EXAMPLES[market][label]
    period = st.selectbox('데이터 범위', ['5y', '10y', 'max', '2y', '1y'], index=1)
    tf = st.radio('🎯 매매 신호 기준 봉', ['주봉', '일봉', '월봉'], index=0, horizontal=True, help='선택한 봉에서만 SCR 매수/매도 신호를 계산합니다. 다른 차트는 참고용 지표입니다.')
    multi_view = st.checkbox('월봉 · 주봉 · 일봉 한 화면 비교', value=True)
    lookback = st.selectbox('통합 차트 표시 범위', ['최근 2년', '최근 5년', '전체'], index=0, disabled=not multi_view)
    st.header('② 지표 설정')
    sn = st.number_input('Stochastic 기간', 1, 100, 5)
    sm = st.number_input('Stochastic 평활', 1, 30, 3)
    cn = st.number_input('CCI 기간', 2, 200, 20)
    rn = st.number_input('RSI 기간', 2, 200, 14)
    so = st.number_input('S 과매도', 1., 49., 20.)
    sb = st.number_input('S 과매수', 51., 99., 80.)
    co = st.number_input('CCI 과매도', -500., -1., -100.)
    cb = st.number_input('CCI 과매수', 1., 500., 100.)
    ro = st.number_input('RSI 과매도', 1., 49., 30.)
    rb = st.number_input('RSI 과매수', 51., 99., 70.)
    st.header('③ SCR 판정 규칙')
    mode_label = st.radio('매수·매도 동시 판정', ['엄격: 세 지표 모두 같은 봉에서 기준선 돌파', '순차: 최근 과열·침체 이력 후 동반 복귀'], index=0)
    signal_mode = 'strict' if mode_label.startswith('엄격') else 'staged'
    window = st.number_input('순차 판정 허용 봉 수', min_value=1, max_value=52, value=8, disabled=(signal_mode == 'strict'))
    fee = st.number_input('한쪽 거래 수수료 (%)', 0., 2., 0.10, step=0.01)
    capital = st.number_input('초기 투자금 (가격 표시 통화)', 100., 1e9, 10000., step=1000.)
    execute = st.button('🚀 백테스트 실행', type='primary', use_container_width=True)

st.info(f'선택된 티커: **{ticker}** · 신호 기준: **{tf}** · 가격은 야후 금융의 보정 시세(분할·배당 반영) · 봉 마감 신호 → **다음 봉 시가** 체결 · 수수료 편도 {fee:.2f}%')
if not execute:
    st.markdown('**시작 방법:** 왼쪽에서 종목과 주기를 고르고 **백테스트 실행**을 누르세요. 각 차트는 실제 데이터가 수신될 때만 생성됩니다.')
    st.stop()

p = Params(int(sn), int(sm), int(cn), int(rn), float(so), float(sb), float(co), float(cb), float(ro), float(rb), float(fee), float(capital))
try:
    with st.spinner('시세 다운로드 및 SCR 계산 중...'):
        daily = load_prices(ticker, period)
        frame = resample_ohlc(daily, {'일봉':'D', '주봉':'W','월봉':'M'}[tf])
        if len(frame) < max(p.cci_n, p.rsi_n, p.stoch_n+p.stoch_smooth)+5:
            st.error('해당 기간/주기에는 계산할 봉 수가 부족합니다. 데이터 범위를 늘리세요.')
            st.stop()
        data = signals(indicators(frame, p), p, mode=signal_mode, window=int(window))
        equity, trades, stats = run_backtest(data, p)
except Exception as exc:
    st.error(f'데이터 조회/계산 실패: {exc}')
    st.stop()

st.subheader('SCR 신호 발생 횟수')
sig_cols = st.columns(4)
sig_cols[0].metric('매수 신호', f"{stats['Buy signals']}회")
sig_cols[1].metric('매도 신호', f"{stats['Sell signals']}회")
sig_cols[2].metric('완료된 매수→매도', f"{stats['Trades']}회")
sig_cols[3].metric('마지막 봉 미체결 신호', '있음' if stats['Unfilled final signal'] else '없음')
st.caption(f'판정: {mode_label}. 신호는 매수·매도가 번갈아 발생하는 상태형이며 미보유/보유 여부와 독립적인 전체 후보 횟수는 아닙니다.')
if signal_mode == 'strict':
    st.info('원문 문구를 문자 그대로 적용: 이전 봉에서 S·C·R 모두 과매도 기준 이하 → 이번 봉에서 모두 초과하면 매수. 매도는 이전 봉 모두 과매수 이상 → 이번 봉 모두 미만. 같은 봉 동시 돌파는 매우 드물 수 있습니다.')
else:
    st.info(f'대안 가설: 최근 {int(window)}봉 사이 세 지표가 각각 과매도/과매수 상태를 경험하고, 현재 봉에 적어도 하나가 기준선을 돌파하며 세 지표가 모두 정상 범위로 돌아오면 신호. 원문 공식으로 확정된 방식은 아닙니다.')
cols = st.columns(5)
for col, key, fmt in zip(cols, ['Return %','CAGR %','MDD %','Win rate %','Trades'], ['{:.1f}%']*4+['{}']):
    val = stats[key]
    col.metric({'Return %':'SCR 수익률', 'CAGR %':'SCR CAGR','MDD %':'SCR MDD','Win rate %':'종료된 거래 승률','Trades':'완료 거래수'}[key], fmt.format(val) if pd.notna(val) else 'N/A')
st.caption(f"동일 투자금 단순보유 수익률: {stats['B&H return %']:.1f}% · 현재 미청산 포지션: {'있음' if stats['Open position'] else '없음'} · 종료되지 않은 거래는 승률에서 제외")
if stats['Unfilled final signal']:
    st.warning('마지막 봉에 발생한 신호는 다음 봉이 없어 미체결 처리됐습니다.')

fig = make_subplots(rows=4, cols=1, shared_xaxes=True, vertical_spacing=.035,
                    row_heights=[.55,.15,.15,.15], subplot_titles=['OHLC + 매수/매도 신호','Stochastic','CCI','RSI'])
fig.add_trace(go.Candlestick(x=data.index, open=data.Open,high=data.High,low=data.Low,close=data.Close,name=ticker), row=1,col=1)
for col, name, symbol, color in [('Buy','매수 신호','triangle-up','#00aa71'),('Sell','매도 신호','triangle-down','#ef4444')]:
    points = data[data[col]]
    fig.add_trace(go.Scatter(x=points.index,y=points.Low*.98 if col=='Buy' else points.High*1.02,
                             mode='markers',marker=dict(symbol=symbol,size=13,color=color),name=name),row=1,col=1)
for row, line, top, bottom in [(2,'S',p.stoch_ob,p.stoch_os),(3,'C',p.cci_ob,p.cci_os),(4,'R',p.rsi_ob,p.rsi_os)]:
    fig.add_trace(go.Scatter(x=data.index, y=data[line],mode='lines',name=line,line=dict(width=1.6)),row=row,col=1)
    fig.add_hline(y=top,line_dash='dot',line_color='#db6674',row=row,col=1)
    fig.add_hline(y=bottom,line_dash='dot',line_color='#35aaaf',row=row,col=1)
    # Shade only the parts of an indicator that actually enter an extreme zone.
    # Two traces form each colored region: its threshold and the indicator value.
    # NaN breaks regions at bars where the threshold is not exceeded.
    series = data[line]
    for zone, mask, threshold, fill_color in [
        ('과매수', series >= top, top, 'rgba(235,80,91,0.32)'),
        ('과매도', series <= bottom, bottom, 'rgba(23,174,172,0.34)'),
    ]:
        threshold_y = pd.Series(float(threshold), index=data.index).where(mask)
        shaded_y = series.where(mask)
        fig.add_trace(go.Scatter(
            x=data.index, y=threshold_y, mode='lines',
            line=dict(width=0), showlegend=False, hoverinfo='skip',
            connectgaps=False), row=row, col=1)
        fig.add_trace(go.Scatter(
            x=data.index, y=shaded_y, mode='lines',
            line=dict(width=0), fill='tonexty', fillcolor=fill_color,
            name=f'{zone} 영역', legendgroup=zone, showlegend=(row == 2),
            hoverinfo='skip', connectgaps=False), row=row, col=1)
# Shared-x-axis vertical signal lines span OHLC, S, C, R panels.
# Red = buy signal date; Blue = sell signal date (not next-bar execution).
for signal_name, color in [('Buy', '#e53935'), ('Sell', '#1565c0')]:
    for signal_date in data.index[data[signal_name]]:
        fig.add_vline(x=signal_date.to_pydatetime(), line_color=color,
                      line_width=1.7, opacity=.82, row='all', col=1)
fig.update_layout(height=850,xaxis_rangeslider_visible=False,legend_orientation='h',margin=dict(l=35,r=20,t=60,b=20))
if multi_view:
    # Exactly ONE authoritative set of SCR signals: the user-selected timeframe.
    # Supporting timeframes have indicators only. No independent buy/sell signals.
    all_frames = {}
    for caption, frequency in [('월봉', 'M'), ('주봉', 'W'), ('일봉', 'D')]:
        ohlc = resample_ohlc(daily, frequency)
        if len(ohlc) >= max(p.cci_n, p.rsi_n, p.stoch_n + p.stoch_smooth) + 5:
            all_frames[caption] = indicators(ohlc, p)
    st.subheader(f'월봉 · 주봉 · 일봉 통합 비교 | 🎯 {tf} 신호 기준')
    st.caption(f'매수/매도는 오직 **{tf} SCR**에서 발생합니다. 세 차트의 빨강/파랑 수직선은 전부 동일한 {tf} 신호 확정일입니다. 나머지 봉에서는 매매 신호를 계산하지 않습니다.')
    colnames = [f'{"★ " if x == tf else ""}{x} ({"매매 신호 기준" if x == tf else "보조 지표"})' for x in ['월봉','주봉','일봉']]
    multi = make_subplots(rows=4, cols=3, shared_xaxes='columns',
                          vertical_spacing=.045, horizontal_spacing=.035,
                          column_titles=colnames, row_heights=[.49,.17,.17,.17])
    period_years = {'최근 2년': 2, '최근 5년': 5, '전체': None}[lookback]
    last_date = daily.index.max()
    left_bound = (last_date - pd.DateOffset(years=period_years)) if period_years else None
    base_events = [(sigdate, signal, '#e53935' if signal == 'Buy' else '#1565c0')
                   for signal in ('Buy','Sell') for sigdate in data.index[data[signal]]]
    for col, timeframe in enumerate(['월봉', '주봉', '일봉'], start=1):
        f = all_frames.get(timeframe)
        if f is None:
            st.warning(f'{timeframe} 지표 계산에 필요한 데이터가 부족합니다. 데이터 범위를 늘려 주세요.')
            continue
        multi.add_trace(go.Candlestick(x=f.index,open=f.Open,high=f.High,low=f.Low,close=f.Close,
                                       name=timeframe,showlegend=False),row=1,col=col)
        # Only reference-timeframe signals; plot markers on its own price series.
        if timeframe == tf:
            for signal, marker, color in [('Buy','triangle-up','#e53935'),('Sell','triangle-down','#1565c0')]:
                t = data[data[signal]]
                multi.add_trace(go.Scatter(x=t.index,y=t.Low*.975 if signal=='Buy' else t.High*1.025,
                                           mode='markers', marker=dict(symbol=marker,size=10,color=color),
                                           showlegend=False, name=f'{tf} {signal}'),row=1,col=col)
        for row, field, upper, lower, line_color in [
                (2,'S',p.stoch_ob,p.stoch_os,'#e98181'),
                (3,'C',p.cci_ob,p.cci_os,'#21aaa7'),
                (4,'R',p.rsi_ob,p.rsi_os,'#62c989')]:
            series = f[field]
            multi.add_trace(go.Scatter(x=f.index,y=series,mode='lines',
                                       line=dict(color=line_color,width=1.3),
                                       name=field,showlegend=False),row=row,col=col)
            multi.add_hline(y=upper,line_color='#db6674',line_dash='dot',line_width=1,row=row,col=col)
            multi.add_hline(y=lower,line_color='#35aaaf',line_dash='dot',line_width=1,row=row,col=col)
            for mask, threshold, shade in [(series>=upper,upper,'rgba(235,80,91,.30)'),
                                            (series<=lower,lower,'rgba(23,174,172,.32)')]:
                multi.add_trace(go.Scatter(x=f.index,y=pd.Series(float(threshold),index=f.index).where(mask),
                                           mode='lines',line=dict(width=0),showlegend=False,
                                           hoverinfo='skip',connectgaps=False),row=row,col=col)
                multi.add_trace(go.Scatter(x=f.index,y=series.where(mask),mode='lines',
                                           line=dict(width=0),fill='tonexty',fillcolor=shade,
                                           showlegend=False,hoverinfo='skip',connectgaps=False),row=row,col=col)
        # A single signal date is mirrored to all twelve subplots.
        for sigdate, signal, color in base_events:
            if left_bound is not None and sigdate < left_bound:
                continue
            for rr in range(1,5):
                multi.add_vline(x=sigdate.to_pydatetime(),line_color=color,
                                line_width=1.25,opacity=.75,row=rr,col=col)
        if left_bound is not None:
            multi.update_xaxes(range=[left_bound,last_date + pd.Timedelta(days=14)],col=col)
        multi.update_xaxes(rangeslider_visible=False,row=1,col=col)
    multi.update_layout(height=780,margin=dict(l=25,r=12,t=50,b=28),
                        showlegend=False,hovermode='x',dragmode='zoom')
    for rr, title in [(1,'가격'),(2,'Stoch'),(3,'CCI'),(4,'RSI')]:
        multi.update_yaxes(title_text=title,row=rr,col=1)
    st.plotly_chart(multi,use_container_width=True)
    st.caption('미래 데이터 주의: 월봉과 주봉 보조선의 최종 봉은 미완성일 수 있습니다. 특히 일봉 신호 시점에 그 달 최종 월봉 값을 이미 알았던 것으로 해석하지 마세요. 아래 보조 지표 요약은 신호일 당시 마지막으로 완료된 일·주·월 봉만 사용합니다.')

    # As-of snapshots for every base signal. A higher-timeframe bar is excluded
    # until its calendar period has actually finished (conservative, no lookahead).
    def completed_context(frame: pd.DataFrame, timeframe: str, event_date: pd.Timestamp) -> pd.DataFrame:
        past = frame.loc[frame.index <= event_date]
        if past.empty:
            return past
        if timeframe == tf:
            # The selected reference bar is the source of the signal itself.
            return past
        if timeframe == '주봉':
            # Strictly previous Friday completed before this event date.
            past = past.loc[past.index.to_period('W-FRI').end_time.normalize() <= event_date]
        elif timeframe == '월봉':
            past = past.loc[past.index.to_period('M').end_time.normalize() <= event_date]
        return past

    context_rows = []
    for sigdate, signal, _ in base_events:
        rec = {'신호일':sigdate.date().isoformat(), '기준 봉':tf, '신호':'매수' if signal=='Buy' else '매도'}
        for timeframe in ['월봉','주봉','일봉']:
            f = all_frames.get(timeframe)
            past = completed_context(f,timeframe,sigdate) if f is not None else pd.DataFrame()
            if not past.empty:
                final = past.iloc[-1]
                rec[f'{timeframe} 확인 봉'] = past.index[-1].date().isoformat()
                for field in ['S','C','R']:
                    rec[f'{timeframe} {field}'] = round(float(final[field]),2) if pd.notna(final[field]) else None
        context_rows.append(rec)
    st.subheader(f'{tf} 매매 신호 시점의 월봉·주봉·일봉 지표')
    if context_rows:
        context_df = pd.DataFrame(context_rows).sort_values('신호일')
        st.dataframe(context_df, use_container_width=True, hide_index=True)
        st.download_button('신호 시점 보조 지표 CSV',context_df.to_csv(index=False).encode('utf-8-sig'),
                           file_name=f'{ticker}_{tf}_scr_context.csv',mime='text/csv')
    else:
        st.info('기준 봉에서 발생한 SCR 매수·매도 신호가 없습니다.')
    with st.expander(f'{tf} 상세 차트 열기'):
        st.plotly_chart(fig,use_container_width=True)
else:
    st.plotly_chart(fig,use_container_width=True)

st.subheader('자산곡선 · SCR vs 단순보유')
eq_fig = go.Figure()
for name in ['Equity','Buy & hold']:
    eq_fig.add_trace(go.Scatter(x=equity.index,y=equity[name],name={'Equity':'SCR','Buy & hold':'단순보유'}[name]))
eq_fig.update_layout(height=320,margin=dict(l=25,r=20,t=20,b=30),yaxis_title='초기 투자금 기준 자산')
st.plotly_chart(eq_fig,use_container_width=True)
st.subheader('모든 SCR 신호 발생 날짜와 지표값')
signal_rows = data.loc[data['Buy'] | data['Sell'], ['Open', 'Close', 'S', 'C', 'R', 'Buy', 'Sell']].copy()
if signal_rows.empty:
    st.info('선택한 기간에 SCR 신호가 없습니다.')
else:
    for k in ('S','C','R'):
        signal_rows['이전 '+k] = data[k].shift(1).loc[signal_rows.index]
    signal_rows.insert(0, '신호', ['매수' if b else '매도' for b in signal_rows['Buy']])
    signal_rows = signal_rows.drop(columns=['Buy', 'Sell']).rename(columns={'Open':'시가', 'Close':'종가', 'S':'Stochastic', 'C':'CCI', 'R':'RSI'})
    signal_rows.index.name = '신호 확정일'
    st.dataframe(signal_rows.style.format({'시가':'{:,.2f}', '종가':'{:,.2f}', 'Stochastic':'{:.2f}', 'CCI':'{:.2f}', 'RSI':'{:.2f}', '이전 S':'{:.2f}', '이전 C':'{:.2f}', '이전 R':'{:.2f}'}), use_container_width=True)
    st.download_button('전체 신호·지표 CSV 다운로드', signal_rows.to_csv().encode('utf-8-sig'), file_name=f'{ticker}_scr_all_signals.csv', mime='text/csv')
st.caption('지표가 과매수 기준을 넘으면 붉은색, 과매도 기준 아래로 내려가면 청록색으로 면적을 채웁니다. 기준선과 영역은 왼쪽 설정값에 따라 바뀝니다.')
st.caption('차트의 빨간 세로선은 매수 신호 확정일, 파란 세로선은 매도 신호 확정일입니다. 두 선은 가격·Stochastic·CCI·RSI 패널을 모두 가로지릅니다. 실제 매매 가격은 다음 봉 시가입니다.')
st.subheader('매수 신호부터 매도 신호까지 · 거래별 수익률')
st.caption('수익률은 신호가 확정된 봉의 종가가 아니라 다음 봉 시가 매수·매도 기준이며, 매수·매도 수수료를 차감합니다. 신호일과 체결일을 각각 표시합니다.')
if trades.empty:
    st.write('완료된 거래가 없습니다. (신호가 없거나 매수 포지션이 아직 열려 있을 수 있습니다.)')
else:
    st.dataframe(trades, use_container_width=True, hide_index=True)
    st.download_button('거래 내역 CSV',trades.to_csv(index=False).encode('utf-8-sig'),file_name=f'{ticker}_scr_trades.csv',mime='text/csv')
st.download_button('지표·시세 CSV',data.to_csv().encode('utf-8-sig'),file_name=f'{ticker}_scr_signals.csv',mime='text/csv')
with st.expander('모델 가정·한계 (중요)'):
    st.markdown('''- **SCR 원문 미확정**: 엄격 모드에서는 전 봉에서 세 지표 모두 극단구간, 현재 봉에서 모두 돌파할 때만 신호. 순차 모드에서는 최근 설정한 봉 수 안에 각 지표가 극단구간을 경험하고 함께 복귀할 때 신호. 두 가지 모두 원문 제작자의 정확한 알고리즘으로 검증된 것은 아닙니다.
- **세로선**: 빨간색은 매수 신호, 파란색은 매도 신호로 봉 마감 확정일을 표시합니다. 선은 4개 패널에 공통 적용됩니다.
- **신호 빈도**: 매수와 매도가 번갈아 발생하는 포지션 상태형 SCR 횟수입니다. 미보유/보유와 무관한 독립 신호 전수 탐색과는 다릅니다.
- **미래정보 방지**: 봉 마감으로 확인한 신호를 다음 봉 시가에 체결. 다만 야후 수정가격의 배당 반영은 거래 가능한 실제 체결가와 차이가 있을 수 있음.
- **체결**: 전액 매수/전량 매도, 롱 전용, 소수점 주식 허용, 슬리피지·세금·환전비용·현금이자 제외.
- **주봉·월봉**: 일별 시세를 집계. 현재 진행 중인 마지막 주/월의 불완전 봉은 실시간 조회에서 포함될 수 있으므로 장중 실거래 신호로 사용 금지.
- **성과**: 진입 중인 잔여 포지션은 종가로 평가. 마지막 봉 신호는 체결하지 않음. 승률은 완료 거래만 계산.
- **단순보유**: 최초 시가에서 1회 매수한 비교 기준(수수료 단순 근사), 월봉 등 기간별 값은 평가 기준에 따라 달라질 수 있음.
- **가격**: 야후가 돌려준 조정 OHLC로 계산, 일부 시장 데이터의 정확성·완전성 보장 불가. 상장폐지 종목 누락 등 생존편향 가능.
''')
