# UI Product Requirements Document

## Overview

**What is this UI for?**
<!-- One or two sentences describing the purpose of the application. -->
A web-based console to manage firmware states for FireFly.  This will cover multiple applications and hardware types (Controller, Client, etc).

**Who will use it?**
<!-- e.g. "Just me", "a small internal team", "non-technical operators" -->
This is an internal tool, used by me.  However, I want to build the tool in a way that it can be leveraged by multiple people with varying permissions.

**Where will it run?**
<!-- e.g. "Desktop browser only", "must work on mobile too" -->
Almost exclusively on the desktop.  But it should be responsive if I want to run it from my phone.

**Deployment?**
The application will be deployed via a GitHub action and stored in S3.  The user will interact with pre-compiled files stored in an S3 bucket (via CloudFormation).  As part of this PRD you should also build out the ability to compile and deploy the output.  The SAM templates must also be created to create and delete the S3 bucket and other CloudFormation stacks required.

---

## Navigation

<!--
Describe the top-level structure of the app. How do users move between pages?
Is there a sidebar? A top navigation bar? Just list the pages/sections and how
they relate to each other.

Example:
  - Top navigation bar with links: Firmware | Settings
  - Clicking a row in the Firmware list takes you to the Firmware Detail page
  - A "Back" button on detail pages returns to the list
-->
I prefer the navigation to be behind a hamburger menu that explodes on the left side of the window.  The panel will feature a link for firmware. In the future, additional links will be added to manage other aspects of the FireFly-Cloud application (such as changing logging verbosity, but that is out of scope for now).

---

## Pages

<!--
One section per page or view. Copy this block as many times as needed.
The "Page" heading should be the name you'd give to the page or tab.
-->

### Page: Login

**Purpose:**
<!-- What is this page for? What problem does it solve? -->
Allows the user to authenticate themselves to the system and prevents unknown/unauthorized users from accessing the sytem.

**How do you get here?**
<!-- e.g. "This is the home page", "Clicking a row in the firmware list" -->
The user will visit https://firefly.p5software.com in their browser.

**What is displayed?**
<!--
List the information shown on this page. Be specific about what fields matter.
Don't worry about layout — just describe what the user needs to see.

Example:
  - A table of all firmware records, showing: version, product ID, application,
    status, and upload date
  - Each row is clickable
  - The table can be filtered by status
-->
For now, we will stub this page out and not require authorization, but I do want to add the page now.  When the user goes to this page they see a single "Login" button that they can click.

**What actions can the user take?**
<!--
List the buttons, links, or interactions on this page and what they do.

Example:
  - "Download" button — opens the firmware ZIP download link in a new tab
  - "Change Status" dropdown — allows transitioning the firmware to the next status
  - "Delete" button — asks for confirmation, then deletes the firmware
-->
The user can click the login button.

**Error and loading states:**
<!--
Describe what should happen in edge cases. Leave blank to accept defaults.

Example:
  - Show a spinner while data is loading
  - If the API returns an error, show the error message from the response
  - If the table is empty, show "No firmware records found"
-->
Because there are no other fields at this time, there are no errors to display to the user.  All clicks of the Login button will be permitted.

### Page: Firmware

**Purpose:**
<!-- What is this page for? What problem does it solve? -->
Allows the user to see all firmware defined in the system.  It is essentially a list of the firmware in a table view.

**How do you get here?**
<!-- e.g. "This is the home page", "Clicking a row in the firmware list" -->
From the hamburger menu -> Firmware.  The user will also be taken here immediately after logging in.

**What is displayed?**
<!--
List the information shown on this page. Be specific about what fields matter.
Don't worry about layout — just describe what the user needs to see.

Example:
  - A table of all firmware records, showing: version, product ID, application,
    status, and upload date
  - Each row is clickable
  - The table can be filtered by status
-->
A table of firmware that have been defined.  At the top of the table should be filters for each column except release status.  The application, Product ID, version, and release status should all be displayed.  The table is paginated with 10 rows shown by default.  The user can see up to 100 rows by selecting a dropdown at the bottom (10, 50, and 100 are options).  The columns can be sorted ascending or descending.  The initial sort order of the displayed firmware is by the record creation date/time, with the most recent record being shown at the top.  There are two checkboxes: Hide Deleted (default checked) and Show Released (default unchecked).  This is more or less a dashboard for the logged in user to see firmware that needs to have actions taken on them, but they also have the ability to view all the firmware with the checkboxes above.  How these are decorated (on/off switches or checkboxes) is fine with me.  The UI should feel modern.  The rows should be banded.

The release status chip should have different colors based on the state, as well as iconography.

The table is not updated automatically.  The user can click a refresh button on the table or refresh the page to see updates.

At the end of each row should be an elipsis.  Clicking it brings up options to set the status of the firmware, or to delete the firmware.  The top-most option should be "Details", which does the same thing as if the row were clicked.  If the user attempts to delete the firmware, a modal should appear confirming that they want to delete the firmware.  The modal should include the application, version, branch, commit, and zip name.

**What actions can the user take?**
<!--
List the buttons, links, or interactions on this page and what they do.

Example:
  - "Download" button — opens the firmware ZIP download link in a new tab
  - "Change Status" dropdown — allows transitioning the firmware to the next status
  - "Delete" button — asks for confirmation, then deletes the firmware
-->
The user can click any of the firmware for more information.  When they do, the firmware detail modal appears.  While this may not be a separate page, I have documented it as a separate page.

**Error and loading states:**
<!--
Describe what should happen in edge cases. Leave blank to accept defaults.

Example:
  - Show a spinner while data is loading
  - If the API returns an error, show the error message from the response
  - If the table is empty, show "No firmware records found"
-->
While the data is loading, a skeleton layout.  If there are no records to show, show a message where the data would be simply saying "No firwmare records found".

### Page: Firmware Details Modal

**Purpose:**
<!-- What is this page for? What problem does it solve? -->
Displays all the detail about the firmware that was clicked.  More or less a UI for the DynamoDB record.  The window has an "X" in the upper-right hand side that the user must click to close it.

**How do you get here?**
<!-- e.g. "This is the home page", "Clicking a row in the firmware list" -->
The user must click one of the firmware versions to bring up this modal.  Also, the URL should be able to be shared between users to bring up a particular firmware details modal.

**What is displayed?**
<!--
List the information shown on this page. Be specific about what fields matter.
Don't worry about layout — just describe what the user needs to see.

Example:
  - A table of all firmware records, showing: version, product ID, application,
    status, and upload date
  - Each row is clickable
  - The table can be filtered by status
-->
The following fields are shown.  None are editable:

- Application
- Product ID + Class
- Branch
- Commit Hash
- Created Date (displayed in the users preferred format, with the time/date corrected for their local timezone)
- Release Status, which can be moved from state to state based on the existing rules in the state machine.
- If the release status is DELETED, an information box showing "This record will be deleted on <date, formatted the same way as Created Date above>."
- Uploaded date (formatted the same way that created date is formatted)
- A link to download the binary, which should be deocrated with iconography.  When clicking the link it should invoke the lambda.  It shouldn't create pre-signed URLs every time the page loads, only when the user requests it.
- Zip file name
- Zip file size in the most logical size (KB, MB)
- A widget is availble to "See manifest files".  When exploded, each of the files included in the manifest are shown, along with their file size (again in KB or MB depending on the most logical) and their sha256.
- The user should see a "Delete" button on this page if the firmware hasn't already been marked for deletion.  If the user attempts to delete the firmware, a modal should appear confirming that they want to delete the firmware.  The modal should include the application, version, branch, commit, and zip name.

**What actions can the user take?**
<!--
List the buttons, links, or interactions on this page and what they do.

Example:
  - "Download" button — opens the firmware ZIP download link in a new tab
  - "Change Status" dropdown — allows transitioning the firmware to the next status
  - "Delete" button — asks for confirmation, then deletes the firmware
-->
The changes were described above.

**Error and loading states:**
<!--
Describe what should happen in edge cases. Leave blank to accept defaults.

Example:
  - Show a spinner while data is loading
  - If the API returns an error, show the error message from the response
  - If the table is empty, show "No firmware records found"
-->

While loading the window, a skeleton layout should be displayed until the data is retrieved.

---

## Global Behavior

**Loading states:**
<!-- What should happen while the app is waiting for the API to respond?
e.g. "Show a spinner", "Disable buttons", "Show a skeleton layout" -->
Show a skeleton layout while we wait for the API to respond.

Toast messages should be shown to the user when they take one of these actions, which appear in the upper-right side:
 - Green success toast, which appears for 5 seconds before being automatically dismissed (there is also an X on the corner to dismiss it immediately before the timer expires) confirming the action the user took, such as "Firmware deleted", "Release state changed to <state>".
 - Red failure toast, which isn't dismissed until the user clicks the X in the corner to actively dismiss it.  This should include some detail about the error message from the API response.  The actual error data should be logged to the console so a developer can troubleshoot it.  This includes any errors that occur anywhere in the application.

**Error handling:**
<!-- What should happen when an API call fails?
e.g. "Show a red banner at the top of the page with the error message" -->
The toast message described above.

**Success feedback:**
<!-- What should happen after a successful action?
e.g. "Show a brief green confirmation message that fades after 3 seconds" -->
The toast message described above.

**Confirmations:**
<!-- Which actions should ask the user to confirm before proceeding?
e.g. "Deletion should require confirmation. Status changes do not." -->
The user should be shown a confirmation for the following:
- When deleting a firmware
- When changing a firmware to the "RELEASED" state
- When changign the firmware from a "RELEASED" state to a "REVOKED" state.

---

## Look and Feel

<!--
You don't need to specify exact colors or fonts. Just describe the general
feeling you want. These are examples — replace with your own preferences.
-->

**Style:**
<!-- e.g. "Clean and minimal", "Dark mode", "Professional / enterprise",
"Simple, no frills", "Match the FireFly brand colors (list them if known)" -->
Style should be clean and minimal, and support dark mode or light mode based on the systems configuration.  The user should be able to select either light or dark mode to override the system selected color scheme.    Field labels should be smaller than the field values, and be displayed above the value.

**Density:**
<!-- How much information should be shown at once?
e.g. "Compact — I want to see as many rows as possible",
or "Spacious — readability matters more than density" -->
Tables should be compact.  Windows should feel "comfortable" but not compact nor spacious.

**Any specific UI preferences:**
<!-- Anything else about how the interface should look or behave.
e.g. "Status values should be colored badges", "Dates should be human-readable
(e.g. '2 hours ago')", "Timestamps should always be shown in local time" -->
I like the idea of timestamps being relative, but being able to click on it and see the actual timestamp, or take some other action to see the raw date/time.  I'm open to ideas on how to implement that.  Timestamps, which shown, should always be in the date format for the user's local machine, and the timezone offset matching their local time.  Ideally, a user in New York would see a timestamp like this: 01/22/2026 1:07PM EST and a user in california looking at the same record would see 01/22/2026 10:07AM PST.  If a user in France were to look at it, they would see 22/01/2026 17:07 CET.

---

## Out of Scope

<!--
List anything you explicitly do NOT want in this version.
This helps avoid scope creep and keeps the first version simple.

Example:
  - No authentication (will be added later)
  - No pagination (table size is small enough to show everything)
  - No dark mode toggle (pick one and stick with it)
-->
I have described the areas that are out of scope in other places throughout the document.

---

## Open Questions

<!--
List anything you're unsure about that we should discuss before coding starts.

Example:
  - Should the download link open in a new tab or start downloading directly?
  - Should the status badge on the list page auto-refresh, or require a page reload?
-->
Please ask me any questions for clarity.
