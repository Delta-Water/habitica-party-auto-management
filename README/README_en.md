<div align="center">

[简体中文](/README.md)

</div>

# Habitica Party Management Tool

This project provides an automated solution for managing Habitica parties, featuring member activity detection, automatic invitations for new members, automatic removal of long-term inactive members, and daily automatic updates of party descriptions. By interacting with the Habitica API through Python scripts, it significantly enhances party management efficiency.

## Key Features

- **Automatic Party Description Updates**: Retrieves the "Golden Mountain Daily Quote" daily and automatically updates the party description with member activity status information.
- **Member Activity Detection**: Regularly checks the last login time of party members and automatically identifies long-term inactive members.
- **Automatic Removal of Inactive Members**: Automatically sends private messages to members who have not logged in for a set period and removes them from the party.
- **Automatic Invitation of New Members**: Automatically searches for users looking for a party and sends party invitations.
- **More Features Continuously Updated**
- **Comprehensive Logging**: All operations are recorded with detailed logs for easy tracking and troubleshooting.

## Quick Start

1. **Clone the Project**
   
2. **Install Dependencies**  
   Python 3.8 or higher is recommended.  
   Run the following command to install dependencies:  
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Environment Variables**  
   Configure your Habitica User ID and API Key in the `.env` file located in the `./scripts` directory:  
   ```
   HABITICA_USER_ID=Your User ID
   HABITICA_API_KEY=Your API Key
   ```

4. **Run the Scripts**  
   - Recommended Method (Scheduled Execution):  
     Use the Windows Task Scheduler to set up a scheduled task for regularly executing `./start.py`.
   
   - Manual Execution (Optional):  
     - Manage Members (Remove inactive members and invite new ones):  
       ```bash
       python scripts/manage_members.py
       ```
     - Update Party Description:  
       ```bash
       python scripts/update_description.py
       ```

5. **Customize Message Templates**  
   Modify the party description templates and the messages sent when removing members in the `./scripts/documents/` directory as needed.

## Logging and Debugging

All operation logs are saved in the `logs` directory for easy viewing and troubleshooting.

## Contributing

We welcome improvements through Issues or Pull Requests. All contributions must comply with the project's existing license agreement.

## Contact

If you have any questions or suggestions, please contact us via GitHub Issues.