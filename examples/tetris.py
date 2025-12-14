from playduino import (
    GameBlock,
    GameEngine,
    PixelColors,
    WallCorners,
    SpawnDirectives,
    BlockMoves,
    GPButtons,
    GPPeriodicCallback,
    GridSlot,
    GP_BUILDER
)
from itertools import takewhile
from itertools import dropwhile
from itertools import chain_from_iterable
from random import choice
from random import randint


class Tetrominoe(GameBlock):
    cross_corners = [WallCorners.TOP]

    @staticmethod
    def _destroy_filled_rows(engine: 'TetrisGame'):
        def is_hollow_row(row: tuple[GridSlot]):
            if not all(row):
                nonlocal hollow_border
                hollow_border += 1
                shift_blocks.update(chain_from_iterable(row))
                return True
            return False
        
        shift_blocks = set[GameBlock]()
        hollow_border = GameBlock.get_max_length()
        n_filled_rows = 0
        for n_filled_rows, filled_row in enumerate(
            takewhile(
                lambda r: all(r),
                dropwhile(is_hollow_row, engine.grid)
            ),
            1
        ):
            for slot in filled_row:
                engine.destroy_cell(slot)
        if n_filled_rows:
            print(f"HOLLOWBORDER: {hollow_border}")
            def filter_coords(coord: tuple[int, int]):
                return coord[1] < hollow_border

            shift_moves = tuple(
                BlockMoves.SHIFT_DOWN
                for _ in range(n_filled_rows)
            )
            with engine.noclip_enabled() as move:
                for block in shift_blocks:
                    move(block, shift_moves, filter_coords)

    def on_collision(self, other, engine: 'TetrisGame', move):
        if (
            move is BlockMoves.SHIFT_DOWN and
            (isinstance(other, GameBlock) or WallCorners.BOTTOM in other)
        ):
            if not self.is_fully_visible():
                engine.destroy_block(self)
                for block in engine.spawned_blocks():
                    if block is not self:
                        engine.destroy_block(block, False)
            else:
                self._destroy_filled_rows(engine)
            engine.spawn_falling()

class T1(Tetrominoe):
    color = PixelColors.CYAN
    shape = [[1,1,1,1]]

class T2(Tetrominoe):
    color = PixelColors.BLUE
    shape = [
        [1,0,0],
        [1,1,1]
    ]

class T3(Tetrominoe):
    color = PixelColors.ORANGE
    shape = [
        [1,1,1],
        [1,0,0]
    ]

class T4(Tetrominoe):
    color = PixelColors.YELLOW
    shape = [
        [1,1],
        [1,1]
    ]

class T5(Tetrominoe):
    color = PixelColors.GREEN
    shape = [
        [0,1,1],
        [1,1,0]
    ]


class T6(Tetrominoe):
    color = PixelColors.PURPLE
    shape = [
        [0,1,0],
        [1,1,1]
    ]

class T7(Tetrominoe):
    color = PixelColors.RED
    shape = [
        [1,1,0],
        [0,1,1]
    ]


class TetrisGame(GameEngine):
    _TETROMINOES = T1, T2, T3, T4, T5, T6, T7

    def spawn_falling(self):
        self._falling_block = self.spawn(
            choice(self._TETROMINOES),
            (SpawnDirectives.RANDOM, SpawnDirectives.START),
            randint(0, 3)
        )

    def on_init(self):
        def boost_speed():
            if not gamepad.is_pressed(GPButtons.ARROW_UP):
                self._speed = FAST_SPEED

        def slowdown_speed():
            if not gamepad.is_pressed(GPButtons.ARROW_DOWN):
                self._speed = SLOW_SPEED

        def restore_speed():
            if not (
                gamepad.is_pressed(GPButtons.ARROW_UP) or
                gamepad.is_pressed(GPButtons.ARROW_DOWN)
            ):
                self._speed = DOWN_SPEED

        def rotate_cw():
            self._falling_block.move(BlockMoves.ROTATE_CW)

        def rotate_ccw():
            self._falling_block.move(BlockMoves.ROTATE_CCW)

        class SideMove(GPPeriodicCallback):
            def __init__(self):
                super().__init__(SIDE_SPEED)

        class MoveLeft(SideMove):
            def __call__(_):
                if not gamepad.is_pressed(GPButtons.ARROW_RIGHT):
                    self._falling_block.move(BlockMoves.SHIFT_LEFT)

        class MoveRight(SideMove):
            def __call__(_):
                if not gamepad.is_pressed(GPButtons.ARROW_LEFT):
                    self._falling_block.move(BlockMoves.SHIFT_RIGHT)

        SIDE_SPEED = 4
        DOWN_SPEED = 20
        FAST_SPEED = DOWN_SPEED // 2
        SLOW_SPEED = DOWN_SPEED * 2
        self.spawn_falling()
        self._speed = DOWN_SPEED
        gamepad = GP_BUILDER.build(
            "Play",
            [
                GPButtons.ARROW_LEFT,
                GPButtons.ARROW_RIGHT,
                GPButtons.ARROW_UP,
                GPButtons.ARROW_DOWN,
                GPButtons.A,
                GPButtons.B
            ],
            on_press={
                GPButtons.ARROW_DOWN: boost_speed,
                GPButtons.ARROW_UP: slowdown_speed,
                GPButtons.ARROW_LEFT: MoveLeft(),
                GPButtons.ARROW_RIGHT: MoveRight(),
                GPButtons.A: rotate_ccw,
                GPButtons.B: rotate_cw
            },
            on_release={
                GPButtons.ARROW_UP: restore_speed,
                GPButtons.ARROW_DOWN: restore_speed
            }
        )
    
    def on_iteration(self):
        if self.is_nth_iteration(self._speed):
            self._falling_block.move(BlockMoves.SHIFT_DOWN)


            
    
