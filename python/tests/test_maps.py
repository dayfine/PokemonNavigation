import unittest

from pokenav.maps import fetch, grid_source, route_log, svg

DATA = r'''
namespace PokemonAutomation{
namespace PokemonBDSP{
namespace SandgemTown{
//  Read from Bulbapedia's DP map of Sandgem Town (Sandgem_Town_DP.png,
//  560 x 368 px). The tile grid starts 8 px in from the left edge, as on the
//  route maps.
const TileGrid& grid(){
    static const TileGrid grid({
        R"(##D#)",  //   0
        R"(..S.)",  //   1
        R"("".v)",  //   2
    });
    return grid;
}
const TilePos POKEMON_CENTER_DOOR{2, 0};
const TilePos POKEMON_CENTER_SIGN{2, 1};
}
}
}
'''

LOG = [
    '2026-10-30 07:07:09.275]: [Route] West to the Route 201 sign: plan from Sandgem Town (20, 7), Sandgem Town (21, 7):',
    '2026-10-30 07:07:09.275]: [Route] Leg 1/2: east 9 (to wall) to Sandgem Town (29, 7), Sandgem Town (29, 8)',
    '2026-10-30 07:07:13.323]: [Walk] West to the Route 201 sign: east 9 (to wall): blocked after 2800ms, 0 wild battle(s).',
    '2026-10-30 07:07:18.775]: [Route] Leg 2/2: west 40 (to wall) to Route 201 (53, 5), Route 201 (53, 6)',
    '2026-10-30 07:07:29.406]: [Walk] West to the Route 201 sign: west 40 (to wall): limit after 9250ms, 0 wild battle(s).',
    '2026-10-30 07:07:32.638]: [Walk] West to the Route 201 sign: west 40 (to wall): at the wall?: limit after 2000ms, 0 wild battle(s).',
    '2026-10-30 07:08:00.000]: [Route] Back to Route 202: plan from Sandgem Town (29, 2):',
]


class GridSourceTest(unittest.TestCase):
    def test_rows_tiles_and_image(self):
        source = grid_source.parse(DATA)
        self.assertEqual(source.name, 'Sandgem Town')
        self.assertEqual(source.rows, ['##D#', '..S.', '"".v'])
        self.assertEqual(source.width, 4)
        self.assertEqual(source.tiles, {'POKEMON_CENTER_DOOR': (2, 0), 'POKEMON_CENTER_SIGN': (2, 1)})
        self.assertEqual(source.image, 'Sandgem_Town_DP.png')
        self.assertEqual(source.image_size, (560, 368))
        self.assertEqual(source.origin, (8, 0))

    def test_map_label(self):
        self.assertEqual(grid_source.map_label('Route202'), 'Route 202')
        self.assertEqual(grid_source.map_label('JubilifeCity'), 'Jubilife City')


class GridTextTest(unittest.TestCase):
    def test_text_file(self):
        source = grid_source.parse_text(
            '// Map: Sandgem Town\n'
            '//  Read from Bulbapedia (Sandgem_Town_DP.png, 560 x 368 px). The tile grid\n'
            '//  starts 8 px in from the left edge.\n'
            '//   POKEMON_CENTER_DOOR 2 0\n'
            '##D#  //  0\n'
            '..S.\n'
            '"".v\n')
        self.assertEqual(source.name, 'Sandgem Town')
        self.assertEqual(source.rows, ['##D#', '..S.', '"".v'])
        self.assertEqual(source.tiles, {'POKEMON_CENTER_DOOR': (2, 0)})
        self.assertEqual(source.image, 'Sandgem_Town_DP.png')
        self.assertEqual(source.origin, (8, 0))

    def test_games_bdsp_route202(self):
        import os
        path = os.path.join(os.path.dirname(__file__), '..', '..', 'games', 'bdsp', 'maps', 'route202.txt')
        source = grid_source.load(path)
        self.assertEqual(source.name, 'Route 202')
        self.assertEqual((source.width, len(source.rows)), (36, 26))
        self.assertEqual(source.tiles['CATCH_SPOT'], (19, 22))


class RouteLogTest(unittest.TestCase):
    def test_legs_and_how_they_stopped(self):
        walks = route_log.parse(LOG)
        self.assertEqual([w.label for w in walks], ['West to the Route 201 sign', 'Back to Route 202'])
        walk = walks[0]
        self.assertEqual(walk.start, [('Sandgem Town', 20, 7), ('Sandgem Town', 21, 7)])
        self.assertEqual([(l.direction, l.tiles, l.to_wall, l.stop) for l in walk.legs],
                         [('east', 9, True, 'blocked'), ('west', 40, True, 'limit')])
        self.assertEqual(walk.legs[1].ends, [('Route 201', 53, 5), ('Route 201', 53, 6)])

    def test_only_one_label(self):
        self.assertEqual(len(route_log.parse(LOG, 'Back to Route 202')), 1)


class FetchTest(unittest.TestCase):
    def test_archive_url_is_the_hash_path(self):
        self.assertEqual(fetch.archive_url('Sandgem Town DP.png'),
                         'https://archives.bulbagarden.net/media/upload/c/c6/Sandgem_Town_DP.png')


class SvgTest(unittest.TestCase):
    def test_marks_a_wall_leg_that_did_not_stop_at_a_wall(self):
        source = grid_source.parse(DATA)
        walks = route_log.parse(LOG)
        out = svg.render(source, None, walks[:1])
        self.assertIn('POKEMON_CENTER_SIGN', out)
        #  The west leg ends on Route 201, off this map: only the east leg is drawn.
        self.assertIn('1 east 9 (blocked)', out)
        self.assertNotIn('2 west 40', out)


if __name__ == '__main__':
    unittest.main()
