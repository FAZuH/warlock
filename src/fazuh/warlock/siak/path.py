class Path:
    """URL constants for the SIAK NG application.

    Contains the base hostname and specific endpoint paths used for navigation
    and API interaction.
    """

    HOSTNAME = "https://academic.ui.ac.id/"
    AUTHENTICATION = f"{HOSTNAME}main/Authentication"
    LOGOUT = f"{HOSTNAME}main/Authentication/Logout"
    CHANGE_ROLE = f"{HOSTNAME}main/Authentication/ChangeRole"
    WELCOME = f"{HOSTNAME}main/Welcome"
    COURSE_PLAN_EDIT = f"{HOSTNAME}main/CoursePlan/CoursePlanEdit"
