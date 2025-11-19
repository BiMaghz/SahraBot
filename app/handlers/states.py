from aiogram.fsm.state import State, StatesGroup

class GeneralPanelFSM(StatesGroup):
    main_menu = State()
    browse_users = State()
    view_user = State()
    search_user = State()
    confirm_action = State()

class UserCreationFSM(StatesGroup):
    waiting_for_username = State()
    waiting_for_data_and_expiry = State()
    waiting_for_expire_type = State()
    waiting_for_services = State()

class UserEditFSM(StatesGroup):
    menu = State()
    waiting_for_data_limit = State()
    waiting_for_expiry = State()
    waiting_for_note = State()
    waiting_for_services = State()

class UserRenewalFSM(StatesGroup):
    waiting_for_data_and_expiry = State()

class DeleteFlowFSM(StatesGroup):
    waiting_for_duration = State()
    confirm_delete_expired = State()

class NodeFSM(StatesGroup):
    menu = State()
    monitoring_menu = State()