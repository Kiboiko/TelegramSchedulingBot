from aiogram import BaseMiddleware, types
from typing import Callable, Dict, Any, Awaitable
from services.storage_service import storage


class RoleCheckMiddleware(BaseMiddleware):
    async def __call__(
            self,
            handler: Callable[[types.Update, Dict[str, Any]], Awaitable[Any]],
            event: types.Update,
            data: Dict[str, Any]
    ) -> Any:
        if isinstance(event, Message) and event.text == '/start':
            return await handler(event, data)

        current_state = await data['state'].get_state() if data.get('state') else None
        if current_state == BookingStates.INPUT_NAME:
            return await handler(event, data)

        if isinstance(event, Message):
            user_id = event.from_user.id
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id
        else:
            return await handler(event, data)

        if not storage.has_user_roles(user_id):
            if isinstance(event, Message):
                await event.answer(
                    "⏳ Ваш аккаунт находится на проверке.\n"
                    "Обратитесь к администратору для получения доступа.\n Телефон администратора: +79001372727",
                    reply_markup=ReplyKeyboardRemove()
                )
            elif isinstance(event, CallbackQuery):
                await event.answer(
                    "⏳ Обратитесь к администратору для получения доступа \n Телефон администратора: +79001372727",
                    show_alert=True
                )
            return

        return await handler(event, data)