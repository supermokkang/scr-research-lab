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
st.caption('한국 · 미국 · 일본 | Stochastic + CCI + RSI | 연구용 가설 모델 v0.1')
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
    tf = st.radio('봉 주기', ['주봉', '일봉', '월봉'], horizontal=True)
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
    fee = st.number_input('한쪽 거래 수수료 (%)', 0., 2., 0.10, step=0.01)
    capital = st.number_input('초기 투자금 (가격 표시 통화)', 100., 1e9, 10000., step=1000.)
    execute = st.button('🚀 백테스트 실행', type='primary', use_container_width=True)

st.info(f'선택된 티커: **{ticker}** · 가격은 야후 금융의 보정 시세(분할·배당 반영) · 봉 마감 신호 → **다음 봉 시가** 체결 · 수수료 편도 {fee:.2f}%')
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
        data = signals(indicators(frame, p), p)
        equity, trades, stats = run_backtest(data, p)
except Exception as exc:
    st.error(f'데이터 조회/계산 실패: {exc}')
    st.stop()

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
fig.update_layout(height=850,xaxis_rangeslider_visible=False,legend_orientation='h',margin=dict(l=35,r=20,t=60,b=20))
st.plotly_chart(fig,use_container_width=True)

st.subheader('자산곡선 · SCR vs 단순보유')
eq_fig = go.Figure()
for name in ['Equity','Buy & hold']:
    eq_fig.add_trace(go.Scatter(x=equity.index,y=equity[name],name={'Equity':'SCR','Buy & hold':'단순보유'}[name]))
eq_fig.update_layout(height=320,margin=dict(l=25,r=20,t=20,b=30),yaxis_title='초기 투자금 기준 자산')
st.plotly_chart(eq_fig,use_container_width=True)
st.subheader('종료된 거래 내역')
if trades.empty:
    st.write('완료된 거래가 없습니다. (신호가 없거나 매수 포지션이 아직 열려 있을 수 있습니다.)')
else:
    st.dataframe(trades, use_container_width=True, hide_index=True)
    st.download_button('거래 내역 CSV',trades.to_csv(index=False).encode('utf-8-sig'),file_name=f'{ticker}_scr_trades.csv',mime='text/csv')
st.download_button('지표·시세 CSV',data.to_csv().encode('utf-8-sig'),file_name=f'{ticker}_scr_signals.csv',mime='text/csv')
with st.expander('모델 가정·한계 (중요)'):
    st.markdown('''- **SCR 원문 미확정**: 3개 과매도/과매수 조건을 각자 한 번 이상 충족한 뒤 세 값이 모두 기준선을 회복/이탈하면 신호. 같은 봉일 필요 없음. 신호 이력은 포지션 전환 때 초기화됨.
- **미래정보 방지**: 봉 마감으로 확인한 신호를 다음 봉 시가에 체결. 다만 야후 수정가격의 배당 반영은 거래 가능한 실제 체결가와 차이가 있을 수 있음.
- **체결**: 전액 매수/전량 매도, 롱 전용, 소수점 주식 허용, 슬리피지·세금·환전비용·현금이자 제외.
- **주봉·월봉**: 일별 시세를 집계. 현재 진행 중인 마지막 주/월의 불완전 봉은 실시간 조회에서 포함될 수 있으므로 장중 실거래 신호로 사용 금지.
- **성과**: 진입 중인 잔여 포지션은 종가로 평가. 마지막 봉 신호는 체결하지 않음. 승률은 완료 거래만 계산.
- **단순보유**: 최초 시가에서 1회 매수한 비교 기준(수수료 단순 근사), 월봉 등 기간별 값은 평가 기준에 따라 달라질 수 있음.
- **가격**: 야후가 돌려준 조정 OHLC로 계산, 일부 시장 데이터의 정확성·완전성 보장 불가. 상장폐지 종목 누락 등 생존편향 가능.
''')
