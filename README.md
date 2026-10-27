# Finger Pods

Clicky, wearable text input for the wearable computing era — finger clips that let you type on any surface, in any light, with the muscle memory you already have.

> **Hackathon:** [Meta AI Developer Hackathon (Cerebral Valley)](https://cerebralvalley.ai/e/meta-ai-developer-hackathon/details)

> **Scope for this hackathon:** one hand only — enough to validate technical feasibility while keeping the system small enough to finish.

---

## Demo

_TODO: add a demo video here once the prototype is ready._

## The problem

People will move from laptops to wearable compute in the next few years. Quality interaction needs information channels in both directions:

| Direction | Visual | Sound | Text |
| --- | --- | --- | --- |
| **Input** | Cameras, screenshots | Microphones | **This project** |
| **Output** | Glasses displays (arriving) | Earbuds / glasses speakers | Subset of visual output |

Five of the six are solved or clearly on their way. **Text input is the gap.**

### Why existing text-input solutions fall short

1. **Speech-to-text** — convenient, but unusable in quiet places and for private information.
2. **Camera-tracked virtual keyboards** — fail outside the camera field of view and in the dark, and tapping a table gives no satisfying tactile feedback.
3. **Wristbands that track finger movement** — do not reach keyboard-comparable typing speed.
4. **Wearable chorded / alternative keyboards** — require learning a new skill and still slower than a standard keyboard.

## The solution

Wearable **finger clips** that sense finger configuration and provide satisfying, tactile button clicks:

- **One clip on each finger.**
- **Magnets** on the index finger and pinky.
- **Magnetometers** on the thumb, middle, and ring fingers.
- **Multiple physical buttons per clip**, positioned for easy access and a crisp, satisfying click across different finger positions. More buttons also simplify keystroke recognition: each button narrows the set of possible keystrokes the system needs to distinguish.

While typing, every keystroke involves a unique finger configuration. Two magnets read by three magnetometers, plus the button states, therefore produce a **unique signature per keystroke** — which a small ML model classifies into a key.

Why this can win:

- Works on **any surface**, in **any light**, with no camera in the loop.
- Real **physical clicks**, not tapping a table.
- **No new skill to learn** — most people already touch-type, so muscle memory does the work.

## Open questions this project explores

1. **Comfort** — can clips be worn for a long time? (See disclosure below: partially explored pre-hackathon.)
2. **Technical feasibility** — are magnet + magnetometer signatures distinct and stable enough to classify keystrokes reliably?

## How it works

```text
Finger pose for a key
  -> magnets (index, pinky) move relative to magnetometers (thumb, middle, ring)
  -> 3x magnetometer readings + button presses form a feature vector
  -> ML classifier predicts the key
  -> character is emitted live
```

## Hackathon plan

| Stage | Deliverable |
| --- | --- |
| 1. Hardware | One-hand prototype: clips, magnets, magnetometers, buttons, wiring |
| 2. Firmware | Stream synchronised sensor + button readings to a computer |
| 3. Data | Tool to record labelled keystrokes |
| 4. Model | Train a classifier on collected data |
| 5. Live demo | Predict keys in real time while typing |

Daily progress: [worklog/](worklog/)

## Pre-hackathon disclosure

In August 2026, I came up with the idea and wanted to validate two key questions:
1. Could the device be comfortable to wear?
2. Could magnetic sensors reliably track finger positions?

I started with comfort, designing [finger clips in Onshape](https://cad.onshape.com/documents/a458d74f05790c53a1d9c083/w/ba0d3bb9b7740cf4850c436d/e/a170be4422ab532e06a19dd8) and 3D-printing several iterations. I also ordered the necessary electronics, including magnets, magnetometers, accelerometers, switches, and other components.

I concluded that 3D-printed parts were far from ideal, but a comfortable wearable seemed achievable with better materials and more engineering time.

After that, I put the project aside and never got around to assembling the hardware, writing firmware, collecting data, or training an ML model. This hackathon is a great opportunity to pick up where I left off, build a working prototype, and finally test whether the magnetic sensing approach works.

## Status

- [x] Idea and problem framing
- [x] Comfort exploration with 3D-printed clips (pre-hackathon, disclosed)
- [x] Parts ordered (pre-hackathon, disclosed)
- [ ] Hardware prototype (one hand)
- [ ] Firmware streaming
- [ ] Data-collection tool
- [ ] Trained classifier
- [ ] Live typing demo
