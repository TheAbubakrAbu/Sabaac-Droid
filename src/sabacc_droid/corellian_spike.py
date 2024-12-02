# corellian_spike.py

import random
import logging
from urllib.parse import quote
import discord
from discord import Embed, ButtonStyle, ui, Interaction
from rules import get_corellian_spike_rules_embed, combine_card_images

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Player:
    '''Initialize a Player with a Discord user.'''

    def __init__(self, user):
        '''Initialize the player with a Discord User.'''

        self.user = user
        self.cards: list[int] = []

    def draw_card(self, deck: list[int]) -> None:
        '''Draw a card from the deck and add it to the player's hand.'''

        if not deck:
            raise ValueError('The deck is empty. Cannot draw more cards.')
        card = deck.pop()
        self.cards.append(card)

    def discard_card(self, card: int) -> bool:
        '''Discard a card from the player's hand. Returns True if successful.'''

        if len(self.cards) <= 1:
            return False
        if card in self.cards:
            self.cards.remove(card)
            return True
        return False

    def replace_card(self, card: int, deck: list[int]) -> bool:
        '''Replace a card in hand with a new one from the deck. Returns True if successful.'''

        if card in self.cards and deck:
            self.cards.remove(card)
            self.draw_card(deck)
            return True
        return False

    def get_cards_string(self) -> str:
        '''Get a string representation of the player's hand.'''

        return ' | ' + ' | '.join(f"{'+' if c > 0 else ''}{c}" for c in self.cards) + ' |'

    def get_total(self) -> int:
        '''Calculate the total sum of the player's hand.'''

        return sum(self.cards)

class CorelliaGameView(ui.View):
    '''Manage the game's state and UI components.'''

    def __init__(self, rounds: int = 3, num_cards: int = 2, active_games: list = None):
        '''Initialize the game view with optional rounds and number of initial cards.'''

        super().__init__(timeout=None)
        self.players: list[Player] = []
        self.game_started = False
        self.current_player_index = -1  # Start at -1 to go to player 0 on first turn
        self.deck: list[int] = []
        self.rounds = rounds
        self.num_cards = num_cards
        self.message = None
        self.current_message = None
        self.active_views: list[ui.View] = []
        self.active_games = active_games
        self.solo_game = False
        self.view_rules_button = ViewRulesButton()
        self.add_item(self.view_rules_button)

    async def reset_lobby(self, interaction: Interaction) -> None:
        '''Reset the game lobby to its initial state.'''

        self.game_started = False
        self.players.clear()
        self.current_player_index = -1

        self.play_game_button.disabled = False
        self.leave_game_button.disabled = False
        self.start_game_button.disabled = True

        embed = Embed(
            title='Sabacc Game Lobby',
            description='Click **Play Game** to join the game.\n\n'
                        f'**Game Settings:**\n{self.rounds} rounds\n{self.num_cards} starting cards\n\n'
                        'Once someone has joined, the **Start Game** button will be enabled.',
            color=0x964B00
        )
        embed.set_footer(text='Corellian Spike Sabacc')
        embed.set_thumbnail(url='https://raw.githubusercontent.com/compycore/sabacc/gh-pages/images/logo.png')

        await interaction.response.edit_message(embed=embed, view=self)

    async def update_game_embed(self) -> None:
        '''Update the game embed to reflect the current player's turn.'''

        current_player = self.players[self.current_player_index]
        card_count = len(current_player.cards)

        description = f'**Players:**\n' + '\n'.join(
            player.user.mention for player in self.players) + '\n\n'
        description += f'**Round {self.rounds_completed}/{self.total_rounds}**\n'
        description += f'It\'s now {current_player.user.mention}\'s turn.\n'
        description += 'Click **Play Turn** to take your turn.\n\n'

        # Attempt to create a list of card backs for the current player's card count
        card_back_url = 'https://raw.githubusercontent.com/TheAbubakrAbu/Sabacc-Droid/refs/heads/main/src/sabacc_droid/images/corellian_spike/card.png'
        card_image_urls = [card_back_url] * card_count

        combined_image_path = None  # Default to None in case image combination fails

        try:
            combined_image_path = combine_card_images(card_image_urls)
        except Exception as e:
            logger.error(f'Failed to combine card images: {e}')
            # Silently continue without the combined image

        # Create embed
        embed = Embed(
            title='Sabacc Game',
            description=description,
            color=0x964B00
        )
        embed.set_thumbnail(url='https://raw.githubusercontent.com/compycore/sabacc/gh-pages/images/logo.png')

        # Attach the image only if it was successfully created
        if combined_image_path:
            embed.set_image(url='attachment://combined_cards.png')

        # Remove previous message's buttons if any
        if self.current_message:
            try:
                await self.current_message.edit(view=None)
            except Exception as e:
                logger.error(f'Error removing previous message buttons: {e}')

        self.clear_items()
        self.add_item(PlayTurnButton(self))
        self.add_item(self.view_rules_button)

        # Send the updated embed
        if combined_image_path:
            # Send with the image
            with open(combined_image_path, 'rb') as f:
                self.current_message = await self.message.channel.send(
                    content=f'{current_player.user.mention}',
                    embed=embed,
                    file=discord.File(f, filename='combined_cards.png'),
                    view=self
                )
        else:
            # Send without the image
            self.current_message = await self.message.channel.send(
                content=f'{current_player.user.mention}',
                embed=embed,
                view=self
            )

    async def update_lobby_embed(self, interaction=None) -> None:
        '''Update the lobby embed with the current list of players and custom settings.'''

        if len(self.players) == 0:
            if interaction:
                await self.reset_lobby(interaction)
            return

        description = f'**Players Joined ({len(self.players)}/8):**\n' + '\n'.join(
            player.user.mention for player in self.players) + '\n\n'

        if self.game_started:
            description += 'The game has started!'
        elif len(self.players) >= 8:
            description += 'The game lobby is full.'

        description += f'**Game Settings:**\n{self.rounds} rounds\n{self.num_cards} starting cards\n\n'

        if len(self.players) < 2:
            description += 'Waiting for more players to join...\n'
            description += 'Click **Start Game** if you want to play with an AI.\n'
        else:
            description += 'Click **Start Game** to begin!\n'

        embed = Embed(
            title='Sabacc Game Lobby',
            description=description,
            color=0x964B00
        )
        embed.set_footer(text='Corellian Spike Sabacc')
        embed.set_thumbnail(url='https://raw.githubusercontent.com/compycore/sabacc/gh-pages/images/logo.png')

        self.start_game_button.disabled = len(self.players) < 1 or self.game_started
        self.play_game_button.disabled = len(self.players) >= 8 or self.game_started

        if interaction:
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await self.message.edit(embed=embed, view=self)

    @ui.button(label='Play Game', style=ButtonStyle.primary)
    async def play_game_button(self, interaction: Interaction, button: ui.Button) -> None:
        '''Add the user to the game when they press Play Game.'''

        user = interaction.user
        if self.game_started:
            await interaction.response.send_message('The game has already started.', ephemeral=True)
            return
        if any(player.user.id == user.id for player in self.players):
            await interaction.response.send_message('You are already in the game.', ephemeral=True)
        elif len(self.players) >= 8:
            await interaction.response.send_message('The maximum number of players (8) has been reached.', ephemeral=True)
        else:
            self.players.append(Player(user))
            await self.update_lobby_embed(interaction)

    @ui.button(label='Leave Game', style=ButtonStyle.danger)
    async def leave_game_button(self, interaction: Interaction, button: ui.Button) -> None:
        '''Remove the user from the game when they press Leave Game.'''

        user = interaction.user
        if self.game_started:
            await interaction.response.send_message('You can\'t leave the game after it has started.', ephemeral=True)
            return
        player = next((p for p in self.players if p.user.id == user.id), None)
        if player:
            self.players.remove(player)
            await self.update_lobby_embed(interaction)
        else:
            await interaction.response.send_message('You are not in the game.', ephemeral=True)

    @ui.button(label='Start Game', style=ButtonStyle.success, disabled=True)
    async def start_game_button(self, interaction: Interaction, button: ui.Button) -> None:
        '''Start the game when the Start Game button is pressed.'''

        user = interaction.user
        if self.game_started:
            await interaction.response.send_message('The game has already started.', ephemeral=True)
            return
        if interaction.user.id not in [player.user.id for player in self.players]:
            await interaction.response.send_message('Only players in the game can start the game.', ephemeral=True)
            return
        if len(self.players) >= 1:
            self.game_started = True

            # Initialize the game
            self.deck = self.generate_deck()
            random.shuffle(self.players)

            # Deal initial cards
            for player in self.players:
                for _ in range(self.num_cards):
                    player.draw_card(self.deck)

            # Initialize round counters
            self.total_rounds = self.rounds
            self.rounds_completed = 1
            self.first_turn = True

            await interaction.response.defer()

            # Start the first turn
            await self.proceed_to_next_player()

            if len(self.players) == 1:
                self.solo_game = True
        else:
            await interaction.response.send_message('Not enough players to start the game.', ephemeral=True)

    def generate_deck(self) -> list[int]:
        '''Generate and shuffle a new deck for the game.'''

        deck = [i for i in range(1, 11) for _ in range(3)]  # Positive cards
        deck += [-i for i in range(1, 11) for _ in range(3)]  # Negative cards
        deck += [0, 0]
        random.shuffle(deck)
        return deck

    async def proceed_to_next_player(self) -> None:
        '''Proceed to the next player's turn or end the round if necessary.'''

        self.current_player_index = (self.current_player_index + 1) % len(self.players)

        if self.current_player_index == 0 and not self.first_turn:
            self.rounds_completed += 1
            if self.rounds_completed > self.total_rounds:
                await self.end_game()
                return

        await self.update_game_embed()

        if self.first_turn:
            self.first_turn = False

    def evaluate_hand(self, player: Player) -> tuple:
        '''Evaluate a player's hand to determine its rank and type.'''

        cards = player.cards
        total = sum(cards)
        hand_type = None
        hand_rank = None
        tie_breakers = []
        counts = {}

        # Count occurrences of each card value
        for card in cards:
            counts[card] = counts.get(card, 0) + 1

        positive_cards = [c for c in cards if c > 0]
        zeros = counts.get(0, 0)

        # Create counts of absolute card values
        abs_counts = {}
        for card in cards:
            abs_card = abs(card)
            abs_counts[abs_card] = abs_counts.get(abs_card, 0) + 1

        if total == 0:
            # Pure Sabacc (two zeros)
            if zeros == 2 and len(cards) == 2:
                hand_type = 'Pure Sabacc'
                hand_rank = 1
                tie_breakers = []
            # Full Sabacc (+10, +10, -10, -10, 0)
            elif sorted(cards) == [-10, -10, 0, +10, +10]:
                hand_type = 'Full Sabacc'
                hand_rank = 2
                tie_breakers = []
            # Yee-Haa (one pair and a zero)
            elif zeros == 1 and any(count >= 2 for value, count in abs_counts.items() if value != 0):
                hand_type = 'Yee-Haa'
                hand_rank = 3
                tie_breakers = [min(abs(c) for c in cards if c != 0)]  # Lower integer wins tie
            # Rule of Two (two pairs)
            elif len([count for count in abs_counts.values() if count >= 2]) >= 2:
                hand_type = 'Rule of Two'
                hand_rank = 4
                tie_breakers = [min(abs(c) for c in cards)]  # Lower integer wins tie
            # Sabacc Pair
            elif any(
                counts.get(value, 0) >= 1 and counts.get(-value, 0) >= 1
                for value in set(cards) if value > 0
            ):
                hand_type = 'Sabacc Pair'
                hand_rank = 5
                tie_breakers = [min(abs(c) for c in cards)]  # Lower integer wins tie
            else:
                # Non-specialty hand that equals zero
                hand_type = 'Sabacc'
                hand_rank = 6
                tie_breakers = [
                    min(abs(c) for c in cards),  # Lower integer wins
                    -len(cards),  # More cards wins
                    -sum(positive_cards),  # Higher positive sum wins
                    -max(positive_cards) if positive_cards else float('-inf'),  # Highest single positive value
                ]
        else:
            # Nulrhek hands (not totaling zero)
            hand_type = 'Nulrhek'
            hand_rank = 10
            tie_breakers = [
                abs(total),  # Closest to zero
                0 if total > 0 else 1,  # Positive beats negative
                -len(cards),  # More cards wins
                -sum(positive_cards),  # Higher positive sum wins
                -max(positive_cards) if positive_cards else float('-inf'),  # Highest single positive card
            ]

        return (hand_rank, *tie_breakers), hand_type, total

    async def end_game(self) -> None:
        '''Determine the winner of the game and end it.'''

        if self.solo_game:
            # Add Lando Calrissian AI to the game
            lando = Player(user=type('AIUser', (object,), {'mention': 'Lando Calrissian AI'})())
            lando.draw_card(self.deck)
            lando.draw_card(self.deck)
            self.players.append(lando)

        if not self.players:
            # Handle the case where all players junked
            embed = Embed(
                title='Game Over',
                description='Nobody won because everyone junked!',
                color=0x964B00
            )
            embed.set_thumbnail(url='https://raw.githubusercontent.com/compycore/sabacc/gh-pages/images/logo.png')
            await self.message.channel.send(embed=embed, view=EndGameView())

            if self in self.active_games:
                self.active_games.remove(self)
            return

        evaluated_hands = []
        for player in self.players:
            hand_value, hand_type, total = self.evaluate_hand(player)
            evaluated_hands.append((hand_value, player, hand_type, total))

        evaluated_hands.sort(key=lambda x: x[0])

        results = '**Final Hands:**\n'
        for eh in evaluated_hands:
            _, player, hand_type, total = eh
            results += f'{player.user.mention}: {player.get_cards_string()} (Total: {total}, Hand: {hand_type})\n'

        best_hand_value = evaluated_hands[0][0]
        winners = [eh for eh in evaluated_hands if eh[0] == best_hand_value]

        if len(winners) == 1:
            winner = winners[0][1]
            hand_type = winners[0][2]
            results += f'\n🎉 {winner.user.mention} wins with a **{hand_type}**!'
        else:
            results += '\nIt\'s a tie between:'
            for eh in winners:
                player = eh[1]
                results += f' {player.user.mention}'
            results += '!'

        embed = Embed(
            title='Game Over',
            description=results,
            color=0x964B00
        )
        embed.set_thumbnail(url='https://raw.githubusercontent.com/compycore/sabacc/gh-pages/images/logo.png')
        mentions = ' '.join(player.user.mention for player in self.players if 'AIUser' not in type(player.user).__name__)
        await self.message.channel.send(content=f'{mentions}', embed=embed, view=EndGameView())

        if self in self.active_games:
            self.active_games.remove(self)

class EndGameView(ui.View):
    '''Provide buttons for actions after the game ends.'''

    def __init__(self):
        '''Initialize the view with a View Rules button.'''

        super().__init__(timeout=None)
        self.add_item(ViewRulesButton())

class PlayTurnButton(ui.Button):
    '''Initialize the Play Turn button.'''

    def __init__(self, game_view: CorelliaGameView):
        '''Initialize the button.'''

        super().__init__(label='Play Turn', style=ButtonStyle.primary)
        self.game_view = game_view

    async def callback(self, interaction: Interaction) -> None:
        '''Handle the Play Turn button press.'''

        current_player = self.game_view.players[self.game_view.current_player_index]
        if interaction.user.id != current_player.user.id:
            await interaction.response.send_message('It\'s not your turn.', ephemeral=True)
            return

        # Generate card image URLs dynamically with + prefix for positive numbers
        base_url = 'https://raw.githubusercontent.com/TheAbubakrAbu/Sabacc-Droid/refs/heads/main/src/sabacc_droid/images/corellian_spike/'
        card_image_urls = [
            f'{base_url}{quote(f"+{card}" if card > 0 else str(card))}.png'
            for card in current_player.cards
        ]

        # Attempt to combine card images
        combined_image_path = None
        try:
            combined_image_path = combine_card_images(card_image_urls)
        except Exception as e:
            logger.error(f'Failed to combine card images: {e}')
            # Continue without an image

        # Prepare the embed
        embed = Embed(
            title=f'Your Turn - Round {self.game_view.rounds_completed}/{self.game_view.total_rounds}',
            description=f'**Your Hand:** {current_player.get_cards_string()}\n**Total:** {current_player.get_total()}',
            color=0x964B00
        )
        embed.set_thumbnail(url='https://raw.githubusercontent.com/compycore/sabacc/gh-pages/images/logo.png')

        # Attach the combined image if it was created successfully
        if combined_image_path:
            embed.set_image(url='attachment://combined_cards.png')

        # Create a turn view for player actions
        turn_view = TurnView(self.game_view, current_player)
        self.game_view.active_views.append(turn_view)

        # Send the embed
        if combined_image_path:
            # Send with the combined image
            with open(combined_image_path, 'rb') as f:
                await interaction.response.send_message(
                    embed=embed,
                    view=turn_view,
                    file=discord.File(f, filename='combined_cards.png'),
                    ephemeral=True
                )
        else:
            # Send without the combined image
            await interaction.response.send_message(
                embed=embed,
                view=turn_view,
                ephemeral=True
            )

class TurnView(ui.View):
    '''Provide action buttons for the player's turn.'''

    def __init__(self, game_view: CorelliaGameView, player: Player):
        '''Initialize the turn view.'''

        super().__init__(timeout=30)
        self.game_view = game_view
        self.player = player

    async def interaction_check(self, interaction: Interaction) -> bool:
        '''Ensure that only the current player can interact with the turn view.'''

        if interaction.user.id != self.player.user.id:
            await interaction.response.send_message('It\'s not your turn.', ephemeral=True)
            return False
        return True

    @ui.button(label='Draw Card', style=ButtonStyle.primary)
    async def draw_card_button(self, interaction: Interaction, button: ui.Button) -> None:
        '''Handle the Draw Card action.'''

        self.player.draw_card(self.game_view.deck)

        # Generate card image URLs dynamically
        base_url = 'https://raw.githubusercontent.com/TheAbubakrAbu/Sabacc-Droid/refs/heads/main/src/sabacc_droid/images/corellian_spike/'
        card_image_urls = [
            f'{base_url}{quote(f"+{card}" if card > 0 else str(card))}.png'
            for card in self.player.cards
        ]

        # Attempt to combine card images
        combined_image_path = None
        try:
            combined_image_path = combine_card_images(card_image_urls)
        except Exception as e:
            logger.error(f'Failed to combine card images: {e}')
            # Continue without an image

        embed = Embed(
            title=f'You Drew a Card - Round {self.game_view.rounds_completed}/{self.game_view.total_rounds}',
            description=f'**Your Hand:** {self.player.get_cards_string()}\n**Total:** {self.player.get_total()}',
            color=0x964B00
        )
        embed.set_thumbnail(url='https://raw.githubusercontent.com/compycore/sabacc/gh-pages/images/logo.png')

        # Attach the combined image if it was created successfully
        if combined_image_path:
            embed.set_image(url='attachment://combined_cards.png')

        if combined_image_path:
            # Send with the combined image
            with open(combined_image_path, 'rb') as f:
                await interaction.response.edit_message(
                    embed=embed,
                    view=None,
                    attachments=[discord.File(f, filename='combined_cards.png')]
                )
        else:
            # Send without the combined image
            await interaction.response.edit_message(embed=embed, view=None)

        self.stop()
        await self.game_view.proceed_to_next_player()

    @ui.button(label='Discard Card', style=ButtonStyle.secondary)
    async def discard_card_button(self, interaction: Interaction, button: ui.Button) -> None:
        '''Handle the Discard Card action.'''

        if len(self.player.cards) <= 1:
            await interaction.response.send_message('You cannot discard when you have only one card.', ephemeral=True)
            return

        # Generate card image URLs dynamically
        base_url = 'https://raw.githubusercontent.com/TheAbubakrAbu/Sabacc-Droid/refs/heads/main/src/sabacc_droid/images/corellian_spike/'
        card_image_urls = [
            f'{base_url}{quote(f"+{card}" if card > 0 else str(card))}.png'
            for card in self.player.cards
        ]

        # Attempt to combine card images
        combined_image_path = None
        try:
            combined_image_path = combine_card_images(card_image_urls)
        except Exception as e:
            logger.error(f'Failed to combine card images: {e}')
            # Continue without an image

        card_select_view = CardSelectView(self, action='discard')
        self.game_view.active_views.append(card_select_view)
        embed = Embed(
            title=f'Discard a Card - Round {self.game_view.rounds_completed}/{self.game_view.total_rounds}',
            description='Click the button corresponding to the card you want to discard.',
            color=0x964B00
        )
        embed.set_thumbnail(url='https://raw.githubusercontent.com/compycore/sabacc/gh-pages/images/logo.png')

        if combined_image_path:
            embed.set_image(url='attachment://combined_cards.png')

        if combined_image_path:
            # Send with the combined image
            with open(combined_image_path, 'rb') as f:
                await interaction.response.edit_message(
                    embed=embed,
                    view=card_select_view,
                    attachments=[discord.File(f, filename='combined_cards.png')]
                )
        else:
            # Send without the combined image
            await interaction.response.edit_message(embed=embed, view=card_select_view)

    @ui.button(label='Replace Card', style=ButtonStyle.secondary)
    async def replace_card_button(self, interaction: Interaction, button: ui.Button) -> None:
        '''Handle the Replace Card action.'''

        # Generate card image URLs dynamically
        base_url = 'https://raw.githubusercontent.com/TheAbubakrAbu/Sabacc-Droid/refs/heads/main/src/sabacc_droid/images/corellian_spike/'
        card_image_urls = [
            f'{base_url}{quote(f"+{card}" if card > 0 else str(card))}.png'
            for card in self.player.cards
        ]

        # Attempt to combine card images
        combined_image_path = None
        try:
            combined_image_path = combine_card_images(card_image_urls)
        except Exception as e:
            logger.error(f'Failed to combine card images: {e}')
            # Continue without an image

        card_select_view = CardSelectView(self, action='replace')
        self.game_view.active_views.append(card_select_view)
        embed = Embed(
            title=f'Replace a Card - Round {self.game_view.rounds_completed}/{self.game_view.total_rounds}',
            description='Click the button corresponding to the card you want to replace.',
            color=0x964B00
        )
        embed.set_thumbnail(url='https://raw.githubusercontent.com/compycore/sabacc/gh-pages/images/logo.png')

        if combined_image_path:
            embed.set_image(url='attachment://combined_cards.png')

        if combined_image_path:
            # Send with the combined image
            with open(combined_image_path, 'rb') as f:
                await interaction.response.edit_message(
                    embed=embed,
                    view=card_select_view,
                    attachments=[discord.File(f, filename='combined_cards.png')]
                )
        else:
            # Send without the combined image
            await interaction.response.edit_message(embed=embed, view=card_select_view)

    @ui.button(label='Stand', style=ButtonStyle.success)
    async def stand_button(self, interaction: Interaction, button: ui.Button) -> None:
        '''Handle the Stand action.'''

        # Generate card image URLs dynamically
        base_url = 'https://raw.githubusercontent.com/TheAbubakrAbu/Sabacc-Droid/refs/heads/main/src/sabacc_droid/images/corellian_spike/'
        card_image_urls = [
            f'{base_url}{quote(f"+{card}" if card > 0 else str(card))}.png'
            for card in self.player.cards
        ]

        # Attempt to combine card images
        combined_image_path = None
        try:
            combined_image_path = combine_card_images(card_image_urls)
        except Exception as e:
            logger.error(f'Failed to combine card images: {e}')
            # Continue without an image

        # Prepare the embed
        embed = Embed(
            title=f'You Chose to Stand - Round {self.game_view.rounds_completed}/{self.game_view.total_rounds}',
            description=f'**Your Hand:** {self.player.get_cards_string()}\n**Total:** {self.player.get_total()}',
            color=0x964B00
        )
        embed.set_thumbnail(url='https://raw.githubusercontent.com/compycore/sabacc/gh-pages/images/logo.png')

        # Attach the combined image if it was created successfully
        if combined_image_path:
            embed.set_image(url='attachment://combined_cards.png')

        # Send the embed
        if combined_image_path:
            with open(combined_image_path, 'rb') as f:
                await interaction.response.edit_message(
                    embed=embed,
                    view=None,
                    attachments=[discord.File(f, filename='combined_cards.png')]
                )
        else:
            await interaction.response.edit_message(embed=embed, view=None)

        self.stop()
        await self.game_view.proceed_to_next_player()

    @ui.button(label='Junk', style=ButtonStyle.danger)
    async def junk_button(self, interaction: Interaction, button: ui.Button) -> None:
        '''Handle the Junk action, removing the player from the game.'''

        # Generate card image URLs dynamically (for the player's last hand)
        base_url = 'https://raw.githubusercontent.com/TheAbubakrAbu/Sabacc-Droid/refs/heads/main/src/sabacc_droid/images/corellian_spike/'
        card_image_urls = [
            f'{base_url}{quote(f"+{card}" if card > 0 else str(card))}.png'
            for card in self.player.cards
        ]

        # Attempt to combine card images
        combined_image_path = None
        try:
            combined_image_path = combine_card_images(card_image_urls)
        except Exception as e:
            logger.error(f'Failed to combine card images: {e}')
            # Continue without an image

        # Prepare the embed
        embed = Embed(
            title=f'You Chose to Junk - Round {self.game_view.rounds_completed}/{self.game_view.total_rounds}',
            description='You have given up and are out of the game.',
            color=0x964B00
        )
        embed.set_thumbnail(url='https://raw.githubusercontent.com/compycore/sabacc/gh-pages/images/logo.png')

        # Attach the combined image if it was created successfully
        if combined_image_path:
            embed.set_image(url='attachment://combined_cards.png')

        # Send the embed
        if combined_image_path:
            with open(combined_image_path, 'rb') as f:
                await interaction.response.edit_message(
                    embed=embed,
                    view=None,
                    attachments=[discord.File(f, filename='combined_cards.png')]
                )
        else:
            await interaction.response.edit_message(embed=embed, view=None)

        # Remove the player from the game
        self.game_view.players.remove(self.player)
        self.stop()

        # Check if the game needs to end
        if len(self.game_view.players) < 2:
            await self.game_view.end_game()
        else:
            await self.game_view.proceed_to_next_player()

    async def on_timeout(self) -> None:
        '''Handle the scenario where a player does not make a move within the timeout period.'''

        try:
            channel = self.game_view.current_message.channel
            embed = Embed(
                title='Turn Skipped',
                description=f'{self.player.user.mention} took too long and their turn was skipped.',
                color=0xFF0000
            )
            await channel.send(embed=embed)
            self.stop()
            await self.game_view.proceed_to_next_player()
        except Exception as e:
            logger.error(f'Error during timeout handling: {e}')

    def stop(self) -> None:
        '''Stop the view and remove it from the active views list.'''

        super().stop()
        if self in self.game_view.active_views:
            self.game_view.active_views.remove(self)

class CardSelectView(ui.View):
    '''Initialize the CardSelectView for choosing a card to discard or replace.'''

    def __init__(self, turn_view: TurnView, action: str):
        '''Initialize the card selection view.'''

        super().__init__(timeout=30)
        self.turn_view = turn_view
        self.game_view = turn_view.game_view
        self.player = turn_view.player
        self.action = action
        self.create_buttons()

    def create_buttons(self) -> None:
        '''Create buttons for each card in the player's hand.'''

        for idx, card in enumerate(self.player.cards):
            button = ui.Button(label=f"{'+' if card > 0 else ''}{card}", style=ButtonStyle.primary)
            button.callback = self.make_callback(card, idx)
            self.add_item(button)
            if len(self.children) >= 25:
                break

        self.add_item(GoBackButton(self))

    def make_callback(self, card_value: int, card_index: int):
        '''Create a callback function for a card button.'''

        async def callback(interaction: Interaction) -> None:
            if self.action == 'discard':
                if len(self.player.cards) <= 1:
                    await interaction.response.send_message('You cannot discard when you have only one card.', ephemeral=True)
                    return
                self.player.cards.pop(card_index)
                title = f'You Discarded {card_value} - Round {self.turn_view.game_view.rounds_completed}/{self.turn_view.game_view.total_rounds}'
            elif self.action == 'replace':
                self.player.cards.pop(card_index)
                self.player.draw_card(self.turn_view.game_view.deck)
                title = f'You Replaced {card_value} - Round {self.turn_view.game_view.rounds_completed}/{self.turn_view.game_view.total_rounds}'
            else:
                embed = Embed(title='Unknown Action', description='An error occurred.', color=0xFF0000)
                await interaction.response.edit_message(embed=embed, view=None)
                return

            # Generate card image URLs dynamically
            base_url = 'https://raw.githubusercontent.com/TheAbubakrAbu/Sabacc-Droid/refs/heads/main/src/sabacc_droid/images/corellian_spike/'
            card_image_urls = [
                f'{base_url}{quote(f"+{card}" if card > 0 else str(card))}.png'
                for card in self.player.cards
            ]

            # Attempt to combine card images
            combined_image_path = None
            try:
                combined_image_path = combine_card_images(card_image_urls)
            except Exception as e:
                logger.error(f'Failed to combine card images: {e}')
                # Continue without an image

            # Prepare the embed
            embed = Embed(
                title=title,
                description=f'**Your Hand:** {self.player.get_cards_string()}\n**Total:** {self.player.get_total()}',
                color=0x964B00
            )
            embed.set_thumbnail(url='https://raw.githubusercontent.com/compycore/sabacc/gh-pages/images/logo.png')

            # Attach the combined image if it was created successfully
            if combined_image_path:
                embed.set_image(url='attachment://combined_cards.png')

            # Send the embed
            if combined_image_path:
                # Send with the combined image
                with open(combined_image_path, 'rb') as f:
                    await interaction.response.edit_message(
                        embed=embed,
                        view=None,
                        attachments=[discord.File(f, filename='combined_cards.png')]
                    )
            else:
                # Send without the combined image
                await interaction.response.edit_message(embed=embed, view=None)

            self.stop()
            self.turn_view.stop()
            await self.turn_view.game_view.proceed_to_next_player()

        return callback

    async def interaction_check(self, interaction: Interaction) -> bool:
        '''Ensure that only the current player can interact with the card selection view.'''

        if interaction.user.id != self.player.user.id:
            await interaction.response.send_message('This is not your card selection.', ephemeral=True)
            return False
        return True

    async def on_timeout(self) -> None:
        '''Handle the scenario where a player does not select a card within the timeout period.'''

        try:
            channel = self.game_view.current_message.channel
            embed = Embed(
                title='Turn Skipped',
                description=f'{self.player.user.mention} took too long and their turn was skipped.',
                color=0xFF0000
            )
            await channel.send(embed=embed)
            self.stop()
            self.turn_view.stop()
            await self.turn_view.game_view.proceed_to_next_player()
        except Exception as e:
            logger.error(f'Error during timeout handling: {e}')

    def stop(self) -> None:
        '''Stop the view and remove it from the active views list.'''

        super().stop()
        if self in self.game_view.active_views:
            self.game_view.active_views.remove(self)

class GoBackButton(ui.Button):
    '''Button to go back to the previous view.'''

    def __init__(self, card_select_view: CardSelectView):
        '''Initialize the Go Back button.'''

        super().__init__(label='Go Back', style=ButtonStyle.secondary)
        self.card_select_view = card_select_view

    async def callback(self, interaction: Interaction) -> None:
        '''Handle the Go Back button press.'''

        turn_view = self.card_select_view.turn_view

        # Generate card image URLs dynamically
        base_url = 'https://raw.githubusercontent.com/TheAbubakrAbu/Sabacc-Droid/refs/heads/main/src/sabacc_droid/images/corellian_spike/'
        card_image_urls = [
            f'{base_url}{quote(f"+{card}" if card > 0 else str(card))}.png'
            for card in turn_view.player.cards
        ]

        # Attempt to combine card images
        combined_image_path = None
        try:
            combined_image_path = combine_card_images(card_image_urls)
        except Exception as e:
            logger.error(f'Failed to combine card images: {e}')
            # Continue without an image

        # Prepare the embed
        embed = Embed(
            title=f'Your Turn - Round {turn_view.game_view.rounds_completed}/{turn_view.game_view.total_rounds}',
            description=f'**Your Hand:** {turn_view.player.get_cards_string()}\n**Total:** {turn_view.player.get_total()}',
            color=0x964B00
        )
        embed.set_thumbnail(url='https://raw.githubusercontent.com/compycore/sabacc/gh-pages/images/logo.png')

        # Attach the combined image if it was created successfully
        if combined_image_path:
            embed.set_image(url='attachment://combined_cards.png')

        # Send the embed
        if combined_image_path:
            with open(combined_image_path, 'rb') as f:
                await interaction.response.edit_message(
                    embed=embed,
                    view=turn_view,
                    attachments=[discord.File(f, filename='combined_cards.png')]
                )
        else:
            await interaction.response.edit_message(embed=embed, view=turn_view)

        self.card_select_view.stop()

class ViewRulesButton(ui.Button):
    '''Initialize the View Rules button.'''

    def __init__(self):
        '''Initialize the button.'''

        super().__init__(label='View Rules', style=ButtonStyle.secondary)

    async def callback(self, interaction: Interaction) -> None:
        '''Display the Corellian Spike game rules when the button is pressed.'''

        rules_embed = get_corellian_spike_rules_embed()
        await interaction.response.send_message(embed=rules_embed, ephemeral=True)