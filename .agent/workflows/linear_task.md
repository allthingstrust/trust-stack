---
description: Execute a coding task with full Linear issue tracking (Create -> Implement -> Commit -> Link)
---

# Linear Feature Workflow

This workflow automates the process of handling a coding task while keeping Linear in sync.

## 1. Setup & Discovery
1.  **Understand the Goal**: Analyze the user's request to understand the objective.
2.  **Locate Linear Context**:
    *   List Linear Teams to find the correct Team ID (e.g., "All Things Trust").
    *   List Linear Projects to find the correct Project ID (e.g., "Core Analysis").
    *   *Prompt user if ambiguous.*

## 2. Issue Management (Start)
1.  **Check for Existing Issue**: Search for an existing issue if the user references one.
2.  **Create Issue**: If no issue exists, create a new Linear issue.
    *   Set status to "In Progress".
    *   Assign to "Me" (or the appropriate user).
    *   Use a descriptive title based on the task.
    *   **IMPORTANT**: Save the `issueId` and `issueIdentifier` (e.g., ALL-12) for later.

## 3. Planning & Implementation
1.  **Create Plan**: Create an `implementation_plan.md` artifact.
2.  **Review**: Ask user for approval.
3.  **Implement**: Perform the necessary code changes.
4.  **Verify**: Run tests or manual verification steps.

## 4. Completion & Linking
1.  **Commit Changes**:
    *   Stage changes: `git add .`
    *   Commit with Issue ID: `git commit -m "[Identifier] <Description>"` (e.g., `ALL-12 Replace use_container_width`).
    *   Get Commit Hash: `git rev-parse HEAD`.
2.  **Update Linear**:
    *   Post a comment on the Linear issue with the Commit Link.
    *   **CRITICAL**: Do NOT include local file links to artifacts (e.g. `[walkthrough](file:///...)`). Instead, summarize the key points of the walkthrough directly in the comment.
    *   Update the Issue Status to "In Review".
3.  **Notify User**: Confirm completion with a link to the execution.
