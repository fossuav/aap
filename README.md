# ArduPilot AI Playbooks

## **Overview**

This project provides guidance documents for using Large Language Models (LLMs) to generate and modify code for the ArduPilot autopilot platform.

Three usage modes are supported:

1. **Claude Code** - Anthropic's CLI tool for interactive development with Claude
2. **Gemini CLI** - Google's CLI tool for interactive development with Gemini
3. **Chat-based LLMs** - Traditional prompt-based code generation with any LLM

The playbooks contain rules and constraints that ensure generated code is safe, testable, and consistent with ArduPilot development standards.

---

## **Claude Code Integration**

[Claude Code](https://claude.ai/code) is Anthropic's official CLI tool that provides an interactive development experience. It can read your codebase, make edits, run commands, and understand project context.

### Quick Start

1. Install the playbooks into your ArduPilot repository:
   ```bash
   cd /path/to/ardupilot
   curl -fsSL https://raw.githubusercontent.com/fossuav/aap/main/install-claude.sh | bash
   ```

2. Start Claude Code:
   ```bash
   claude
   ```

Claude Code will automatically read the `CLAUDE.md` files and use them to guide its responses.

### Installed Files

The install script places the following files:

| File | Purpose |
|------|---------|
| `CLAUDE.md` | Build system, architecture overview, C++ development guidelines |
| `libraries/AP_Scripting/CLAUDE.md` | Lua scripting patterns, applet structure, parameter system |
| `libraries/AP_Scripting/CLAUDE_CRSF_MENU.md` | CRSF (Crossfire) menu implementation |
| `libraries/AP_Scripting/CLAUDE_VEHICLE_CONTROL.md` | Vehicle control APIs, movement commands, RC input |
| `libraries/AP_NavEKF3/CLAUDE.md` | EKF3 navigation filter reference and analysis methodology |
| `libraries/AP_HAL_ChibiOS/hwdef/CLAUDE.md` | ChibiOS board porting and hwdef.dat creation |

### Uninstalling

To remove the playbook files from ArduPilot:
```bash
cd /path/to/ardupilot
curl -fsSL https://raw.githubusercontent.com/fossuav/aap/main/uninstall-claude.sh | bash
```

---

## **Gemini CLI Integration**

The [Gemini CLI](https://github.com/google-gemini/gemini-cli) provides a similar interactive development experience using Google's Gemini models.

### Quick Start

1. Install the playbooks into your ArduPilot repository:
   ```bash
   cd /path/to/ardupilot
   curl -fsSL https://raw.githubusercontent.com/fossuav/aap/main/install-gemini.sh | bash
   ```

2. Start Gemini:
   ```bash
   gemini
   ```

Gemini will automatically read the `GEMINI.md` files and use them to guide its responses.

### Installed Files

The install script places the following files:

| File | Purpose |
|------|---------|
| `GEMINI.md` | Build system, architecture overview, C++ development guidelines |
| `libraries/AP_Scripting/GEMINI.md` | Lua scripting patterns, applet structure, parameter system |
| `libraries/AP_Scripting/GEMINI_CRSF_MENU.md` | CRSF (Crossfire) menu implementation |
| `libraries/AP_Scripting/GEMINI_VEHICLE_CONTROL.md` | Vehicle control APIs, movement commands, RC input |

### Uninstalling

To remove the playbook files from ArduPilot:
```bash
cd /path/to/ardupilot
curl -fsSL https://raw.githubusercontent.com/fossuav/aap/main/uninstall-gemini.sh | bash
```

---

## **Chat-Based LLM Usage**

For traditional chat-based LLMs (ChatGPT, Claude web, Gemini web, etc.), you can manually provide playbook context.

### Key Components

To generate code, the LLM requires the following context:

* **API Documentation (docs.lua)** This file is the definitive source for all ArduPilot-specific Lua function signatures and is the final authority on correct API usage.
* **AI Playbook** This file(s) is the rule definitions for code generation telling the LLM what it may and may not do. Without this the LLM will go easily off track
* **Code Digest (digest.txt)** This file contains a snapshot of existing code and tests within the ArduPilot repository. It provides the LLM with the necessary examples to create new code. Unfortunately this digest tends to be quite large and can easily overflow the LLM's context window so it is often necessary to abandon it in favour of merely the first two items.

### Generating a Digest

1. Install [gitingest](https://github.com/cyclotruc/gitingest)
2. Run ```gitingest libraries/AP_Scripting -e '*.cpp' -e '*.c' -e '*.h' -e '*.txt'```
3. A LUA digest will be generated in digest.txt
4. Run ```gitingest Tools/autotest -i arducopter.py -i vehicle_test_suite.py```
5. An autotest digest will be generated in digest.txt

### How to Use This System

The process for generating code is as follows:

1. **Write a Prompt:** Clearly describe the required functionality. Focus on what the code should do, not the implementation details.  
   * *Example Prompt:* "Create a script to control the brightness of my drone's NeoPixel LEDs using an RC switch. It should support three levels: off, medium, and high."
2. **Provide Context:** Give the LLM your prompt, AI playbook, API documentation and, optionally, the digest-lua.txt file.
3. **Generate Artifacts:** The LLM will generate a complete ArduPilot Applet (in the case of lua), which includes:
   * A .lua script file.  
   * A .md documentation file explaining how to set up and use the script.  
4. **Generate Autotest:** For every applet, the LLM should offer to generate a corresponding SITL autotest file. This allows you to verify the script's functionality in a safe, simulated environment.

---

## **Repository Structure**

```
aap/
├── claude/                          # Claude Code playbooks (CLAUDE.md files)
│   ├── CLAUDE.md                    # Root playbook (build, architecture, C++)
│   └── libraries/
│       ├── AP_Scripting/            # Lua scripting playbooks
│       │   ├── CLAUDE.md
│       │   ├── CLAUDE_CRSF_MENU.md
│       │   └── CLAUDE_VEHICLE_CONTROL.md
│       ├── AP_NavEKF3/              # EKF3 navigation filter
│       │   └── CLAUDE.md
│       └── AP_HAL_ChibiOS/hwdef/    # ChibiOS board porting
│           └── CLAUDE.md
├── gemini/                          # Gemini CLI playbooks (GEMINI.md files)
│   ├── GEMINI.md                    # Root playbook (build, architecture, C++)
│   └── libraries/AP_Scripting/      # Lua scripting playbooks
│       ├── GEMINI.md
│       ├── GEMINI_CRSF_MENU.md
│       └── GEMINI_VEHICLE_CONTROL.md
├── cpp/                             # C++ playbooks for chat-based LLMs
│   └── AI_PAIR_PROGRAMMING_PLAYBOOK_CPP.md
├── lua/                             # Lua playbooks for chat-based LLMs
│   ├── AI_PAIR_PROGRAMMING_PLAYBOOK.md
│   ├── AI_CRSF_MENU_PLAYBOOK.md
│   ├── AI_VEHICLE_CONTROL_PLAYBOOK.md
│   ├── AI_GIT_FORMAT_PATCH_PLAYBOOK.md
│   └── docs.lua                     # Lua API documentation
├── install-claude.sh                # Install Claude playbooks to ArduPilot
├── uninstall-claude.sh              # Remove Claude playbooks from ArduPilot
├── install-gemini.sh                # Install Gemini playbooks to ArduPilot
├── uninstall-gemini.sh              # Remove Gemini playbooks from ArduPilot
└── README.md
```

## **License**

This project is licensed under the GNU General Public License v3.0. See `COPYING.txt` for details.
