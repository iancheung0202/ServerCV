# ServerCV | Professional Discord Resumes

Build a verified portfolio of your server contributions. Perfect for staff applications and sharing your achievements in the Discord community. 

Check out the website at https://servercv.com.

## Motivation

I’ve been using AI for a while, but mostly in the classic "copy–paste from chatbot into VS Code" workflow. It worked, but it always felt like I was babysitting the model more than actually coding with it. With the release of Gemini 3 and all the hype around agentic workflows, I finally decided to try using agents directly inside my editor instead of bouncing between websites.

But I already knew from experience that asking an LLM to generate a complex project from scratch is extremely hit-or-miss. Most of the time, it gives you something impressive-looking but completely not what you actually wanted. So this project, I started by writing a very simple skeleton code myself from scratch, just enough structure so the agents had something grounded to build on.

From there, most of the code was created through agents using Gemini Pro 3 (and occasionally Grok Code Fast 1). Instead of writing myself, I guided the agents through iterative prompting, architecture adjustments, and plenty of debugging AI-generated code. It took around 50 prompts and 8 full hours to get from the skeleton code to the full initial commit (it definitely would have taken more than 8 days without AI).

Agentic development is exciting, but still far from magic. The agents handled boilerplate and repetitive tasks really well, but debugging was chaotic. Sometimes they nailed entire features in one go; other times they confidently broke things that previously worked. I still had to understand the code deeply and manually steer the agents when they drifted off course. But despite the rough edges, building ServerCV this way was genuinely fun. Watching an agent reason, plan, and attempt to build features that just previously existed in my brain felt surreal. 

## How It Works

1. **Connect**: Login with Discord to securely access your server history.
2. **Verify**: Request endorsement from server owners or admins. Once approved, your role is added to your verified resume.
3. **Showcase**: Share your unique profile link with server owners and applications.

## Tech Stack

- **Backend**: Python, Flask
- **Database**: Firebase Realtime Database
- **Authentication**: Discord OAuth2
- **Frontend**: HTML5, Tailwind CSS (via CDN), JavaScript
- **Payments**: PayPal Integration

## License

This project is licensed under the [MIT License](LICENSE).