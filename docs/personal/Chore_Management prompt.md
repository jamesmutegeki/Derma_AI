# Master prompt for Claude code(making Claude.md and architectual_patterns.md specific to the software)
Analyze this codebase and create a CLAUDE.md file following these principles:
 
1. Keep it under 150 lines total - focus only on universally applicable information
2. Cover the essentials: WHAT (tech stack, project structure), WHY (purpose), and HOW (build/test commands)
3. Use Progressive Disclosure: instead of including all instructions, create a brief index pointing to other markdown files in .claude/docs/ for specialized topics
4. Include file:line references instead of code snippets
5. Assume I'll use linters for code style - don't include formatting guidelines
 
Structure it as: project overview, tech stack, key directories/their purposes, essential build/test commands, and a list of additional documentation files Claude should check when relevant.
 
Additionally, extract patterns you observe into separate files:
- .claude/docs/architectural_patterns.md - document the architectural patterns, design decisions, and conventions used (e.g., dependency injection, state management, API design patterns). Make sure these are patterns that appear in multiple files.
 
Reference these files in the CLAUDE.md's "Additional Documentation" section.

# Second prompt
Use the above prompt to write me a Claude.md file and modular step-by-step prompts to create the web application, following the above prompt's content to describe the structure Claude will follow as it creates a chore assignment web application. It will be themed white and blue, but I should be able to turn it to dark mode. The assignments are mopping, cooking, cleaning the toilet, and washing plates. I should also allow me to add a custom chore, and it should also enable me to allocate time for this chore, and each chore should have its own color. It should be in a calendar format. It should allow input of a photo so that when I hover over the day, the faces of the people and their chores pop out with the time they need to do those chores.


This is a great project to streamline household management. Since you are building this from scratch, I have designed the `CLAUDE.md` and architectural patterns based on a modern, responsive tech stack that handles the "hover/pop-out" photo requirements and calendar logic efficiently (React, Tailwind CSS, and Lucide for icons).

### CLAUDE.md

Markdown

```
# ChoreFlow: Chore Assignment Web App

## WHAT: Project Overview & Tech Stack
A calendar-based web application for household chore management.
- **Frontend:** React (Vite), Tailwind CSS
- **State Management:** React Context API (Chore/User data)
- **Icons/UI:** Lucide-React, Headless UI (for Modals/Transitions)
- **Persistence:** LocalStorage (initial) / Supabase (future)

## WHY: Core Purpose
To provide a visual, time-allocated schedule for domestic tasks with a specialized "photo-hover" interface for quick identification of responsible parties.

## HOW: Essential Commands
- **Install:** `npm install`
- **Dev:** `npm run dev`
- **Build:** `npm run build`
- **Lint:** `npm run lint`
- **Test:** `npm test`

## Key Directories
- `src/components/calendar/`: Core calendar grid and day cells
- `src/components/ui/`: Reusable buttons, inputs, and modals
- `src/hooks/`: `useChores.js`, `useTheme.js`
- `src/context/`: State providers for global theme and chore data
- `src/utils/`: Date manipulation logic and color mapping

## Additional Documentation
See these files in `.claude/docs/` for specific implementation details:
1. **Architectural Patterns:** Design decisions for state and UI.
2. **Component Specs:** Details on the Hover-Popout and Time-Allocation logic.
3. **Theming:** Guide to the Blue/White and Dark Mode implementation.
```

---

### .claude/docs/architectural_patterns.md

Markdown

```
# Architectural Patterns & Design Decisions

## 1. Color-to-Chore Mapping
To ensure chores have consistent unique colors (e.g., Cooking = Blue, Mopping = Green), we use a lookup utility:
- Ref: `src/utils/colors.js:5`

## 2. Hover-Triggered Pop-outs (The "Face-Pop" Pattern)
Instead of standard tooltips, the app uses a "Portal" pattern to ensure chore details (names + faces) appear above all calendar layers without clipping.
- Implementation: `src/components/calendar/DayCell.jsx:42`

## 3. Progressive Theme Injection
Dark mode is handled via a `ThemeProvider` that toggles a `.dark` class on the root element. Colors are mapped to CSS variables (primary: white/blue).
- Ref: `src/context/ThemeContext.jsx:12`

## 4. Chore Entity Schema
Each chore is an object with: `id`, `type` (default or custom), `timeAllocated`, `assignedTo` (User object with `photoURL`), and `color`.
```

---

### Modular Creation Prompts

Follow these prompts in order to build the application step-by-step:

#### Step 1: Foundation & Theming

> **Prompt:** Set up a React project using Vite and Tailwind CSS. Implement a `ThemeContext` that supports a "White and Blue" light mode and a high-contrast Dark Mode. Create the basic layout with a toggle switch for the theme. Ensure the primary light mode uses a clean white background with blue accents (`#3b82f6`).

#### Step 2: The Calendar Engine

> **Prompt:** Build a responsive Month-View calendar component. Each day cell should be able to render a list of assigned chores. Use `date-fns` for date logic. Chores should display as small colored dots or bars on the calendar day.

#### Step 3: Chore Management & Customization

> **Prompt:** Create the chore logic. Include the four defaults (Mopping, Cooking, Cleaning Toilet, Washing Plates) with assigned colors. Add a "Custom Chore" form that allows me to input a chore name, select a color, and allocate a specific time duration (e.g., 30 mins, 1 hour).

#### Step 4: Photo Integration & Data Structure

> **Prompt:** Implement the user assignment system. Each person should have a name and a photo upload (local URL). Update the chore object to include a `time` slot and a link to the assigned person's profile.

#### Step 5: The "Hover-Pop" Interactive Layer

> **Prompt:** Create the interactive hover effect for calendar days. When I hover over a day, a pop-out modal/tooltip should appear showing the assigned person’s face (photo) and their specific chores for that day, including the allocated time. Use Framer Motion or Tailwind transitions for a smooth "pop" effect.

Would you like to start with the code for the **Foundation & Theming** step?

To run the app, you will follow the standard Node.js workflow established in the `CLAUDE.md` file we created. Since you are a Computer Science student, you likely already have the environment set up, but here are the exact steps to get it running on your machine (like your HP ProBook).

### 1. Prerequisites

Ensure you have **Node.js** and **npm** installed. You can check this by running:

Bash

```
node -v
npm -v
```

### 2. Setup & Installation

Open your terminal in the project's root directory and run:

Bash

```
# Install all dependencies (React, Tailwind, Lucide, etc.)
npm install
```

### 3. Launching the Development Server

Run the following command to start the app locally:

Bash

```
npm run dev
```

- **The Output:** The terminal will provide a local URL, typically `http://localhost:5173`.
    
- **Access:** Open that link in your browser (Chrome or Safari on your iPhone/Pixel to test responsiveness).
    

---

### Quick Reference (from your CLAUDE.md)

|**Task**|**Command**|
|---|---|
|**Start Dev Server**|`npm run dev`|
|**Build for Production**|`npm run build`|
|**Check for Errors**|`npm run lint`|
|**Run Unit Tests**|`npm test`|

### Troubleshooting for your setup:

- **Port Conflicts:** If port `5173` is busy, Vite will automatically try `5174`.
    
- **Mobile Testing:** Since you use an iPhone 13 Pro Max and a Pixel 7a, you can view the app on your phones by ensuring they are on the same Wi-Fi as your laptop and navigating to your laptop's IP address (e.g., `[http://192.168.1.](http://192.168.1.)XX:5173`).
    

Would you like the code for the **Step 1: Foundation & Theming** prompt to begin building the actual files?

## Navigation
← Back to [[📇Life]]
