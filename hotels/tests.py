from django.test import TestCase, Client
from django.urls import reverse
from hotels.models import Hotel
from rooms.models import RoomType, RoomImage

class HotelPublicProfileTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        # Create a test hotel
        self.hotel = Hotel.objects.create(
            name="Grand Plaza Resort",
            city="Kampala",
            country="Uganda",
            star_rating=5.0,
            description="Luxury resort in the heart of the city."
        )
        # Create a test room type
        self.room_type = RoomType.objects.create(
            hotel=self.hotel,
            name="Deluxe Suite",
            description="Spacious suite with breathtaking city views.",
            base_price=250000.00
        )
        
    def test_hotel_profile_rendering(self):
        url = reverse("hotel:hotel_profile", kwargs={"slug": self.hotel.slug})
        response = self.client.get(url)
        
        # Verify response is 200 OK
        self.assertEqual(response.status_code, 200)
        
        # Verify custom context values
        self.assertIn("hotel", response.context)
        self.assertIn("room_types_json", response.context)
        
        # Verify serialized room type JSON
        room_types_json = response.context["room_types_json"]
        self.assertIn("Deluxe Suite", room_types_json)
        self.assertIn("Spacious suite with breathtaking city views", room_types_json)
        self.assertIn("250000", room_types_json)
