# SCR Research Lab — 무료 한·미·일 주식 백테스트 MVP

## 기능
- 한국/미국/일본 종목 티커 입력 (예: `005930.KS`, `SOXX`, `7203.T`)
- yfinance 일별 데이터 다운로드(온라인 환경에서 동작), 일봉·주봉·월봉 선택
- Stochastic Fast(평활값), CCI, Wilder RSI를 활용한 가설형 SCR 신호
- 다음 봉 시가 체결, 편도 수수료, 장기 보유와 수익률·CAGR·MDD 비교
- 캔들차트, 3개 지표, 신호 마커, 거래 목록 CSV

## 5분 내 무료 웹사이트 배포
1. GitHub에서 새 저장소를 만든다 (초기에는 **private** 가능).
2. 이 압축파일의 내용을 풀고, `app.py`, `engine.py`, `requirements.txt`, `.streamlit/config.toml` 및 `README.md`를 그대로 업로드한다. **ZIP 파일 자체를 올리지 않는다.**
3. https://share.streamlit.io/ 에 GitHub 계정으로 로그인한다.
4. `Create app`에서 저장소 및 브랜치 선택, Main file path에 `app.py` 입력 후 Deploy.
5. 생성된 `*.streamlit.app` 링크에서 백테스트를 사용한다. 첫 실행 시 라이브러리 설치와 서버 시작에 시간이 걸릴 수 있다.

공식 안내: https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy

## 로컬 테스트 (선택)
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## 이 전략은 원문의 검증된 복제품이 아님
- 매수: 각 S/C/R이 한 번 이상 과매도 영역에 진입한 뒤, 세 지표가 모두 기준을 회복한 봉 마감에 신호
- 매도: 진입 후 각 S/C/R이 과매수 영역에 진입한 뒤, 세 지표가 모두 아래로 이탈한 봉 마감에 신호
- 체결: 다음 봉 시가. 종가에 신호를 확인하고 같은 종가에 체결하는 잘못된 룩어헤드 백테스트 방지
- 하나의 방향에 대한 진입/매도 추적은 반대 포지션 상태에서 초기화됨
- 손절매·슬리피지·세금·환율·현금이자 없음. 전체 자산 투입. 거래비용은 편도 %
- 지표 원문 파라미터 및 동시 조건, Signal 평활화 여부는 아직 미확정이며 수정이 필요함

## 데이터 제한
- 무료 Yahoo Finance 출처는 비공식 yfinance 라이브러리로 이용한다. 일부 티커, 일부 기간 조회가 실패할 수 있다.
- 배당·분할 조정 가격을 사용하므로 실제 체결 원화/달러/엔화 가격·현금 배당·세금과 다를 수 있다.
- 한국 KOSDAQ은 통상 `.KQ`, KOSPI는 `.KS`, 도쿄 거래소는 `.T`를 사용한다.
- 통화별 자산곡선은 각 티커 거래통화 기준이며 환전수익은 포함하지 않는다.
- 검증용 결과가 아니며 레버리지 ETF에서는 재설정·구조적 괴리 위험이 크다.


## v0.6: 신호 기준 봉 선택
- 사이드바에서 일봉/주봉/월봉 중 매매 신호 기준 봉을 선택합니다 (기본 주봉).
- 선택된 기준 봉으로만 SCR 신호와 백테스트 수익률을 산출합니다.
- 월봉/주봉/일봉 차트의 빨강/파랑 수직선은 모두 같은 기준 봉 신호 날짜를 표시합니다.
- 보조 지표 표는 신호일에 완성된 봉만 선택하여 미래정보 사용을 피합니다.
- 월봉 최종 월말 차트값은 월중 사건 시점의 값으로 사용하지 않습니다.
