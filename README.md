# [개ː소리]
<img width="597" height="151" alt="image" src="https://github.com/user-attachments/assets/f23ff6bf-f916-4e22-bf8c-bc3407a59eae" />


<img width="970" height="663" alt="개솔" src="https://github.com/user-attachments/assets/4cfbd697-ef08-4a4f-bf2b-6532876f869c" />

개소리를 입력으로 받아 코딩 에이전트에게 게임을 만들게 하는 PoC입니다.

[English README](./README.en.md)

- 데모: https://lee-wonjun.github.io/dogsound-hackathon/
- 생성된 게임 소스: [docs/](./docs/)
- 게임 해석 기록: [docs/ANALYSIS.md](./docs/ANALYSIS.md)
- 프로세서 문서: [processor/README.md](./processor/README.md)

## 이게 뭐냐

`processor/`는 마이크 입력을 실시간으로 녹음하고, 침묵 구간 기준으로 입력 덩어리를 나눈 뒤, 그 입력을 짧은 텍스트로 바꿔 Codex 또는 Claude Code에 넘깁니다.

`docs/`에는 이 프로세스로 만든 Phaser 게임이 들어 있습니다. GitHub Pages가 `/docs`를 그대로 서빙하도록 배치했습니다.

## 영감

이 PoC는 Caleb Leak의 [I Taught My Dog to Vibe Code Games](https://www.calebleak.com/posts/dog-game/)와 한국의 음성 코딩 해커톤 [천하제일 입코딩 대회](https://lipcoding.kr/)에서 영감을 받았습니다.

Caleb Leak의 글에서 중요한 부분은 “의미 없는 입력” 자체가 아니라, 그 입력을 게임 기획으로 받아들이게 하는 프롬프트와 피드백 루프였습니다. 입코딩 대회 쪽에서는 키보드 대신 목소리로 개발하는 해커톤 형식이 힌트가 됐습니다.

그래서 이 프로젝트는 “개소리로 게임 만들기”를 해볼 수 있는 작은 실험입니다. 지금은 토크나이저도 PoC용으로 대충 바이브한 상태라, 진짜 언어를 해독한다고 주장하지 않습니다.

## 지금 해본 결과

프로세스를 끝까지 돌려보니 게임은 계속 만들어집니다. 다만 아직 하네스가 약해서, 생성된 게임이 클리어 불가능한 상태로 끝나는 경우가 있습니다.

다음으로 필요한 건 프롬프트를 더 길게 쓰는 게 아니라 피드백 시스템입니다.

- 자동 플레이 가능성 검사
- 승리 조건 도달 가능성 검사
- 에이전트가 볼 수 있는 스크린샷
- 스크립트된 입력 재생
- 클리어 불가능한 빌드를 거절하고 다시 고치게 하는 루프

이 부분만 제대로 깎으면 진짜 “개소리 해커톤”도 열 수 있을 것 같습니다. 웃긴 건 입력이지만, 핵심은 그 입력을 플레이 가능한 결과물로 바꾸는 피드백 루프입니다.

## 프로세서 실행

```bash
cd /home/dldnjs1013/projects/dogsound
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r processor/requirements.txt
python -m processor doctor
```

GPT-5.5 low reasoning으로 실행하는 예시:

```bash
python -m processor listen \
  --ui \
  --agent codex \
  --model gpt-5.5 \
  --reasoning-effort low \
  --workspace /home/dldnjs1013/projects/game \
  --silence-ms 2500 \
  --min-utterance-ms 80 \
  --agent-idle-timeout-seconds 0
```

## 데모 게임 로컬 실행

```bash
cd docs
python3 -m http.server 4174
```

브라우저에서 `http://localhost:4174`를 엽니다.

체크:

```bash
cd docs
npm test
npm run build
```

## 해석 기록 예시

생성된 게임은 구현 전에 “이번 입력을 어떻게 게임 요구사항으로 읽었는지”를 남깁니다. 전체 기록은 [docs/ANALYSIS.md](./docs/ANALYSIS.md)에 있습니다.

예시:

```md
# Input Analysis

Input: `fjdjvtpkplanztunk`

Possible readings considered:

- `dj` and the hard consonants could imply rhythm-first play, with beats and impact timing.
- `vtpk` can be read as compact movement notation: vertical, turn, parkour, kick.
- `plan z tunk` is the clearest semantic cluster: an emergency plan, a final zone, and a heavy dunk/thunk action.

Chosen reading:

Build `Plan Z: Tunk`, a small vertical action-puzzle where the player gathers plan shards in order, then slams the completed plan core into the Zone Z exit. This fits the readable center of the input while using the surrounding hard consonants as movement and collision feel. The scope is a complete single-screen browser game rather than a map-only update because the repository has no existing implementation.
```

## GitHub Pages

이 저장소는 `main` 브랜치의 `/docs` 디렉터리를 GitHub Pages로 배포합니다.
