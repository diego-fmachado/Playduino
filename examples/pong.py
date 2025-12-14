from playduino import (
    GameBlock,
    GameEngine,
    PixelColors,
    WallCorners,
    SpawnDirectives,
    VerticalCorner,
    BlockMoves,
    BlockShift,
    ScreenInfo,
    GPButtons,
    GPPeriodicCallback,
    SpawnDirective,
    GP_BUILDER
)
from random import choice

class Platform(GameBlock):
    color = PixelColors.RED
    shape = [[1,1,1,1,1]]

class Ball(GameBlock):
    color = PixelColors.BLUE
    shape = [[1]]
    _START_MOVES = (
        BlockMoves.SHIFT_UP_LEFT,
        BlockMoves.SHIFT_UP_RIGHT,
        BlockMoves.SHIFT_DOWN_LEFT,
        BlockMoves.SHIFT_DOWN_RIGHT
    )

    def on_spawn(self):
        self._shift = choice(self._START_MOVES)
        self._newborn_span = 2 * ScreenInfo.REFRESH_RATE

    def _apply_shift(self, shift: BlockShift):
        self._shift *= shift
        self.move()   

    def on_collision(self, other, engine: 'PongGame', move):
        if isinstance(other, WallCorners):
            if VerticalCorner in other:
                engine.destroy_block(self)
                engine.spawn_ball()
            else:
                self._apply_shift(BlockMoves.SHIFT_DOWN_LEFT)
        elif (
            self.ref[0] < other.ref[0] or
            self.ref[0] >= other.ref[0] + other.width
        ):
            self._apply_shift(BlockMoves.SHIFT_UP_LEFT)
        else:
            self._apply_shift(BlockMoves.SHIFT_UP_RIGHT)

    def move(self):
        super().move(self._shift)

    def is_newborn(self):
        if self._newborn_span < 0:
            return False
        self._newborn_span -= 1
        return True


class PongGame(GameEngine):
    def on_init(self):
        def spawn_platform(i: int, y_directive: SpawnDirective):
            class MoveLeft(SideMove):
                def __call__(_):
                    if not gamepad.is_pressed(GPButtons.ARROW_RIGHT):
                        platform.move(BlockMoves.SHIFT_LEFT)

            class MoveRight(SideMove):
                def __call__(_):
                    if not gamepad.is_pressed(GPButtons.ARROW_LEFT):
                        platform.move(BlockMoves.SHIFT_RIGHT)

            gamepad = GP_BUILDER.build(
                f"Player {i + 1}",
                buttons,
                on_press={
                    GPButtons.ARROW_LEFT: MoveLeft(),
                    GPButtons.ARROW_RIGHT: MoveRight(),
                }
            )
            platform = self.spawn(Platform, (SpawnDirectives.CENTER, y_directive))

        class SideMove(GPPeriodicCallback):
            def __init__(self):
                super().__init__(2)

        self.spawn_ball()
        buttons = [
            GPButtons.ARROW_LEFT,
            GPButtons.ARROW_RIGHT
        ]
        for i, y_directive in enumerate((
            SpawnDirectives.START,
            SpawnDirectives.END
        )):
            spawn_platform(i, y_directive)

    def spawn_ball(self):
        self._ball = self.spawn(
            Ball,
            (
                SpawnDirectives.CENTER,
                SpawnDirectives.CENTER
            )
        )

    def on_iteration(self):
        if (
            not self._ball.is_newborn() and
            self.is_nth_iteration(10)
        ):
            self._ball.move()
                
                


                



    
