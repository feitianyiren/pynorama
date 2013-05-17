''' navigation.py defines viewing.py related navigation. '''

''' ...And this file is part of Pynorama.
    
    Pynorama is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.
    
    Pynorama is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
    GNU General Public License for more details.
    
    You should have received a copy of the GNU General Public License
    along with Pynorama. If not, see <http://www.gnu.org/licenses/>. '''

from gi.repository import Gtk, Gdk, GLib, GObject
from gettext import gettext as _
import math, time
import preferences

class MouseAdapter(GObject.GObject):
	''' Adapts a widget mouse events '''
	EventMask = (Gdk.EventMask.BUTTON_PRESS_MASK |
	             Gdk.EventMask.BUTTON_RELEASE_MASK |
	             Gdk.EventMask.POINTER_MOTION_MASK |
	             Gdk.EventMask.POINTER_MOTION_HINT_MASK)
	
	# According to the docs, Gtk uses +10 for resizing and +20 for redrawing
	# +15 should dispatch events after resizing and before redrawing
	# TODO: Figure out whether that is a good idea
	IdlePriority = GLib.PRIORITY_HIGH_IDLE + 15
	            
	__gsignals__ = {
		"motion" : (GObject.SIGNAL_RUN_FIRST, None, [object, object]),
		"drag" : (GObject.SIGNAL_RUN_FIRST, None, [object, object, int]),
		"pression" : (GObject.SIGNAL_RUN_FIRST, None, [object, int]),
		"click" : (GObject.SIGNAL_RUN_FIRST, None, [object, int]),
		"start-dragging" : (GObject.SIGNAL_RUN_FIRST, None, [object, int]),
		"stop-dragging" : (GObject.SIGNAL_RUN_FIRST, None, [object, int]),
	}
	
	def __init__(self, widget=None):
		GObject.GObject.__init__(self)
		
		self.__from_point = None
		self.__pressure = dict()
		self.__widget = None
		
		self.__delayed_motion_id = None
		self.__widget_handler_ids = None
		self.__ice_cubes = 0
		
		if widget:
			self.set_widget(widget)
			
	def get_widget(self):
		return self.__widget
		
	def set_widget(self, widget):
		if self.__widget != widget:
			if self.__widget:
				self.__pressure.clear()
				
				for a_handler_id in self.__widget_handler_ids:
					self.__widget.disconnect(a_handler_id)
				self.__widget_handler_ids = None
				
				if self.__delayed_motion_id:
					GLib.source_remove(self.__delayed_motion_id)
					self.__delayed_motion_id = None
				
			self.__widget = widget
			if widget:			
				widget.add_events(MouseAdapter.EventMask)
				self.__widget_handler_ids = [
					widget.connect("button-press-event", self._button_press),
					widget.connect("button-release-event", self._button_release),
					widget.connect("motion-notify-event", self._mouse_motion),
				]
				
	widget = GObject.property(get_widget, set_widget, type=Gtk.Widget)
	
	# icy-wut-i-did-thaw
	@property
	def is_frozen(self):
		return self.__ice_cubes > 0
		
	def freeze(self):
		self.__ice_cubes += 1
		
	def thaw(self):
		self.__ice_cubes -= 1
	
	def is_pressed(self, button=None):
		return bool(self.__pressure if button is None \
		            else self.__pressure.get(button, 0))
	
	# begins here the somewhat private functions
	def _button_press(self, widget, data):
		self.__pressure.setdefault(data.button, 1)
		if not self.is_frozen:
			point = widget.get_pointer()
			self.emit("pression", point, data.button)
		
	def _button_release(self, widget, data):
		if data.button in self.__pressure:
			if not self.is_frozen:
				button_pressure = self.__pressure.get(data.button, 0)
				if button_pressure:
					point = widget.get_pointer()
					if button_pressure == 2:
						self.emit("stop-dragging", point, data.button)
					
					self.emit("click", point, data.button)
				
			del self.__pressure[data.button]
		
	def _mouse_motion(self, widget, data):
		# Motion events are handled idly
		if not self.__delayed_motion_id:
			if not self.__from_point:
				self.__from_point = widget.get_pointer()
				
			self.__delayed_motion_id = GLib.idle_add(
			                                self.__delayed_motion, widget,
			                                priority=MouseAdapter.IdlePriority)
			     
	def __delayed_motion(self, widget):
		self.__delayed_motion_id = None
		
		if not self.is_frozen:
			point = widget.get_pointer()
			if self.__from_point != point:
				for button, pressure in self.__pressure.items():
					if pressure == 1:
						self.__pressure[button] = 2
						self.emit("start-dragging", point, button)
						
					if pressure:
						self.emit("pression", point, button)
				
				self.emit("motion", point, self.__from_point)
				for button, pressure in self.__pressure.items():
					if pressure == 2:
						self.emit("drag", point, self.__from_point, button)
				
		self.__from_point = point
		return False
		
class MouseEvents:
	Nothing  =  0 #0000
	Hovering =  1 #0001
	Dragging = 10 #1010
	Moving   =  3 #0011
	Pressing =  6 #0110
	Clicking =  8 #1000
	
class MetaMouseHandler:
	''' Handles mouse events from mouse adapters for mouse handlers '''
	# It's So Meta Even This Acronym
	def __init__(self):
		self.__adapters = dict()
		self.__handlers = dict()
		self.__pression_handlers = set()
		self.__hovering_handlers = set()
		self.__dragging_handlers = set()
		self.__button_handlers = dict()
		
	def add(self, handler):
		if not handler in self.__handlers:
			self.__handlers[handler] = dict()
			for handler_set in self.__get_handler_sets(handler):
				handler_set.add(handler)
			
			for button in handler.buttons:
				button_set = self.__button_handlers.get(button, set())
				button_set.add(handler)
				self.__button_handlers[button] = button_set
			
	def remove(self, handler):
		if handler in self.__handlers:
			del self.__handlers[handler]
			for handler_set in self.__get_handler_sets(handler):
				handler_set.discard(handler)
			
			for button in handler.buttons:
				self.__button_handlers[button].discard(handler)
	
	def __get_handler_sets(self, handler):
		if handler.handles_pressing:
			yield self.__pression_handlers
			
		if handler.handles_hovering:
			yield self.__hovering_handlers
			
		if handler.handles_dragging:
			yield self.__dragging_handlers
				
	def attach(self, adapter):
		if not adapter in self.__adapters:
			signals = [
				adapter.connect("motion", self._motion),
				adapter.connect("pression", self._pression),
				adapter.connect("start-dragging", self._start_dragging),
				adapter.connect("drag", self._drag),
				adapter.connect("stop-dragging", self._stop_dragging),
			]
			self.__adapters[adapter] = signals
			
	def detach(self, adapter):
		signals = self.__adapters.get(adapter, [])
		for a_signal in signals:
			adapter.disconnect(a_signal)
			
		del self.__adapters[adapter]
		
	def __overlap_button_set(self, handler_set, button):
		button_handlers = self.__button_handlers.get(button, set())
		
		if button_handlers:
			return handler_set & button_handlers
		else:
			return button_handlers
	
	def __basic_event_dispatch(self, adapter, event_handlers,
	                           function_name, *params):
	                           
		widget = adapter.get_widget()
		
		for a_handler in event_handlers:
			data = self.__handlers[a_handler].get(adapter, None)
			function = getattr(a_handler, function_name)
			data = function(widget, *(params + (data,)))
			if data:
				self.__handlers[a_handler][adapter] = data
	
	def _motion(self, adapter, to_point, from_point):
		if adapter.is_pressed():
			hovering = not any((adapter.is_pressed(a_button) \
			                      for a_button, a_button_handlers \
			                      in self.__button_handlers.items() \
			                      if a_button_handlers))
		else:
			hovering = True
			
		if hovering:
			self.__basic_event_dispatch(adapter, self.__hovering_handlers,
			                            "hover", to_point, from_point)
	
	def _pression(self, adapter, point, button):
		active_handlers = self.__overlap_button_set(
		                       self.__pression_handlers, button)
		                       
		if active_handlers:
			self.__basic_event_dispatch(adapter, active_handlers, 
			                            "press", point)
		
	def _start_dragging(self, adapter, point, button):
		active_handlers = self.__overlap_button_set(
		                       self.__dragging_handlers, button)
		                       
		if active_handlers:
			self.__basic_event_dispatch(adapter, active_handlers, 
			                            "start_dragging", point)
		
	def _drag(self, adapter, to_point, from_point, button):		
		active_handlers = self.__overlap_button_set(
		                       self.__dragging_handlers, button)
		                       
		if active_handlers:
			self.__basic_event_dispatch(adapter, active_handlers, 
					                    "drag", to_point, from_point)
			
	def _stop_dragging(self, adapter, point, button):
		active_handlers = self.__overlap_button_set(
                       self.__dragging_handlers, button)
                       
		if active_handlers:
			self.__basic_event_dispatch(adapter, active_handlers, 
				                        "stop_dragging", point)
		                            
class MouseHandler:
	''' Handles mouse events '''
	# The base of the totem pole
	
	def __init__(self):
		self.events = MouseEvents.Nothing
		self.buttons = []
		
	@property
	def handles_pressing(self):
		return self.events & MouseEvents.Pressing == MouseEvents.Pressing
		
	@property
	def handles_hovering(self):
		return self.events & MouseEvents.Hovering == MouseEvents.Hovering
	
	@property
	def handles_dragging(self):
		return self.events & MouseEvents.Dragging == MouseEvents.Dragging
	
	def press(self, widget, point, data):
		pass
	
	def hover(self, widget, to_point, from_point, data):
		pass
	
	def start_dragging(self, widget, point, data):
		pass
	
	def drag(self, widget, to_point, from_point, data):
		pass
		
	def stop_dragging(self, widget, point, data):
		pass
		
class HoverHandler(MouseHandler):
	''' Pans a view on mouse hovering '''
	def __init__(self, speed=1.0, magnify=False):
		MouseHandler.__init__(self)
		self.speed = speed
		self.magnify_speed = magnify
		self.events = MouseEvents.Hovering
	
	def hover(self, view, to_point, from_point, data):
		(tx, ty), (fx, fy) = to_point, from_point
		dx, dy = tx - fx, ty - fy
		
		scale = self.speed
		if not self.magnify_speed:
			scale /= view.get_magnification()
		sx, sy = dx * scale, dy * scale
		
		ax = view.get_hadjustment().get_value()
		ay = view.get_vadjustment().get_value()
		view.adjust_to(ax + sx, ay + sy)

class DragHandler(HoverHandler):
	''' Pans a view on mouse dragging '''
	def __init__(self, speed=-1.0, magnify=False):
		HoverHandler.__init__(self, speed, magnify)
		self.events = MouseEvents.Dragging
		self.buttons = [1]
		
	def start_dragging(self, view, *etc):
		fleur_cursor = Gdk.Cursor(Gdk.CursorType.FLEUR)
		view.get_window().set_cursor(fleur_cursor)
	
	drag = HoverHandler.hover # lol.
	
	def stop_dragging(self, view, *etc):
		view.get_window().set_cursor(None)

class MapHandler(MouseHandler):
	''' Adjusts a view to match a point inside.
	    In it's most basic way for "H" being a point in the widget,
	    "C" being the resulting adjustment, "B" being the widget size and
	    "S" being the boundaries of the viewing widget model: C = H / B * S '''
	def __init__(self, margin=32, mapping_mode="proportional"):
		MouseHandler.__init__(self)
		self.buttons = [1]
		self.events = MouseEvents.Pressing
		self.mapping_mode = mapping_mode
		self.margin = margin
		
	def press(self, view, point, data):
		# Clamp mouse pointer to map
		rx, ry, rw, rh = self.get_map_rectangle(view)
		mx, my = point
		x = max(0, min(rw, mx - rx))
		y = max(0, min(rh, my - ry))
		# The adjustments
		hadjust = view.get_hadjustment()
		vadjust = view.get_vadjustment()
		# Get content bounding box
		full_width = hadjust.get_upper() - hadjust.get_lower()
		full_height = vadjust.get_upper() - vadjust.get_lower()
		full_width -= hadjust.get_page_size()
		full_height -= vadjust.get_page_size()
		# Transform x and y to picture "adjustment" coordinates
		tx = x / rw * full_width + hadjust.get_lower()
		ty = y / rh * full_height + vadjust.get_lower()
		view.adjust_to(tx, ty)
		
	def get_map_rectangle(self, view):
		allocation = view.get_allocation()
		
		allocation.x = allocation.y = self.margin
		allocation.width -= self.margin * 2
		allocation.height -= self.margin * 2
		
		if allocation.width <= 0:
			diff = 1 - allocation.width
			allocation.width += diff
			allocation.x -= diff / 2
			
		if allocation.height <= 0:
			diff = 1 - allocation.height
			allocation.height += diff
			allocation.y -= diff / 2
		
		if self.mapping_mode == "square":
			if allocation.width > allocation.height:
				smallest_side = allocation.height
			else:
				smallest_side = allocation.width
			
			half_width_diff = (allocation.width - smallest_side) / 2
			half_height_diff = (allocation.height - smallest_side) / 2
			
			return (allocation.x + half_width_diff,
				    allocation.y + half_height_diff,
				    allocation.width - half_width_diff * 2,
				    allocation.height - half_height_diff * 2)
			
		elif self.mapping_mode == "proportional":
			hadjust = view.get_hadjustment()
			vadjust = view.get_vadjustment()
			full_width = hadjust.get_upper() - hadjust.get_lower()
			full_height = vadjust.get_upper() - vadjust.get_lower()
			fw_ratio = allocation.width / full_width
			fh_ratio = allocation.height / full_height
						
			if fw_ratio > fh_ratio:
				smallest_ratio = fh_ratio
			else:
				smallest_ratio = fw_ratio
			
			transformed_width = smallest_ratio * full_width
			transformed_height = smallest_ratio * full_height
			
			half_width_diff = (allocation.width - transformed_width) / 2
			half_height_diff = (allocation.height - transformed_height) / 2
			
			return (allocation.x + half_width_diff,
				    allocation.y + half_height_diff,
				    allocation.width - half_width_diff * 2,
				    allocation.height - half_height_diff * 2)
			
		else:
			return (allocation.x, allocation.y,
			        allocation.width, allocation.height)
			        
class SpinHandler(MouseHandler):
	''' Spins a view '''
	
	SpinThreshold = 5
	SoftRadius = 25
	
	def __init__(self, frequency=1, fixed_pivot=None):
		MouseHandler.__init__(self)
		self.buttons = [3]
		self.events = MouseEvents.Dragging
		# Number of complete turns in the view per revolution around the pivot
		self.frequency = frequency 
		# Use a fixed pivot instead of the dragging start point
		self.fixed_pivot = fixed_pivot
		
	def start_dragging(self, view, point, data):
		if self.fixed_pivot:
			w, h = view.get_allocated_width(), view.get_allocated_height()
			sx, sy = self.fixed_pivot
			pivot = sx * w, sy * h
		else:
			pivot = point
			
		return pivot, view.get_pin(pivot)
	
	def drag(self, view, to_point, from_point, data):
		pivot, pin = data
		
		# Get vectors from the pivot
		(tx, ty), (fx, fy), (px, py) = to_point, from_point, pivot
		tdx, tdy = tx - px, ty - py
		fdx, fdy = fx - px, fy - py
		
		# Get rotational delta, multiply it by frequency
		ta = math.atan2(tdy, tdx) / math.pi * 180
		fa = math.atan2(fdy, fdx) / math.pi * 180
		rotation_effect = (ta - fa) * self.frequency
		
		# Modulate degrees
		rotation_effect %= 360 if rotation_effect >= 0 else -360
		if rotation_effect > 180:
			rotation_effect -= 360
		if rotation_effect < -180:
			rotation_effect += 360 
			
		# Thresholding stuff
		square_distance = tdx ** 2 + tdy ** 2
		if square_distance > SpinHandler.SpinThreshold ** 2:
			# Falling out stuff
			square_soft_radius = SpinHandler.SoftRadius ** 2
			if square_distance < square_soft_radius:
				fallout_effect = square_distance / square_soft_radius
				rotation_effect *= fallout_effect
			
			# Changing the rotation(finally)
			view.set_rotation(view.get_rotation() + rotation_effect)
			# Anchoring!!!
			view.adjust_to_pin(pin)
			
		return data

class ScaleHandler(MouseHandler):
	''' Zooms a view '''
	
	MinDistance = 10
	
	def __init__(self, pivot=(.5, .5)):
		MouseHandler.__init__(self)
		self.buttons = [2]
		self.events = MouseEvents.Dragging
		self.pivot = pivot
		
	def start_dragging(self, view, point, data):
		w, h = view.get_allocated_width(), view.get_allocated_height()
		x, y = point
		sx, sy = self.pivot
		px, py = sx * w, sy * h
		pivot = px, py
		
		xd, yd = x - px, y - py
		distance = max(ScaleHandler.MinDistance, (xd ** 2 + yd ** 2) ** .5)
		zoom = view.get_magnification()
		zoom_ratio = zoom / distance
		
		return zoom_ratio, pivot, view.get_pin(pivot)
	
	def drag(self, view, to_point, from_point, data):
		zoom_ratio, pivot, pin = data
		
		# Get vectors from the pivot
		(x, y), (px, py) = to_point, pivot
		xd, yd = x - px, y - py
		
		# Get pivot distance, multiply it by zoom ratio
		pd = max(ScaleHandler.MinDistance, (xd ** 2 + yd ** 2) ** .5)
		new_zoom = pd * zoom_ratio
		
		view.set_magnification(new_zoom)
		view.adjust_to_pin(pin)
		
		return data

# This file is not full of avatar references.
NaviList = []

class DragNavi:
	''' This navigator adjusts the view based on only mouse movement '''
	def __init__(self, imageview):
		self.imageview = imageview
		
		self.idling = False
		self.dragging = False
		self.last_step = None
		self.margin_handling_ref = None
		self.moving_timestamp = None
		
		# Setup events
		self.imageview.add_events(Gdk.EventMask.BUTTON_PRESS_MASK |
			Gdk.EventMask.BUTTON_RELEASE_MASK |
			Gdk.EventMask.POINTER_MOTION_MASK |
			Gdk.EventMask.POINTER_MOTION_HINT_MASK)
		
		self.view_handlers = [
			self.imageview.connect("button-press-event", self.button_press),
			self.imageview.connect("button-release-event", self.button_release),
			self.imageview.connect("motion-notify-event", self.motion_event)
			]
		
	def detach(self):
		for handler in self.view_handlers:
			self.imageview.disconnect(handler)
			
		self.imageview.get_window().set_cursor(None)
	
	def button_press(self, widget, data):
		if not DragNavi.RequireClick:
			# In this case, the navi drags without clicking,
			# so we don't need to handle this
			return
			
		if data.button == 1:
			self.dragging = True
			self.last_step = self.imageview.get_pointer()
			fleur_cursor = Gdk.Cursor(Gdk.CursorType.FLEUR)
			self.imageview.get_window().set_cursor(fleur_cursor)
			
			if self.margin_handling_ref is None and self.check_margin(False):
				self.attach_timeout()
			
	def button_release(self, widget, data):
		if not DragNavi.RequireClick:
			return
			
		if data.button == 1:
			self.dragging = False
			self.last_step = None
			self.imageview.get_window().set_cursor(None)
			
			if self.margin_handling_ref is not None:
				self.remove_timeout()
				
	def attach_timeout(self):
		timeout_in_ms = int(1000 * DragNavi.Frequency)
		self.margin_handling_ref = GLib.timeout_add(timeout_in_ms,
		                                            self.margin_handler)
		self.moving_timestamp = time.time()
		
	def remove_timeout(self):
		self.moving_timestamp = None
		GLib.source_remove(self.margin_handling_ref)
		self.margin_handling_ref = None
		
	def motion_event(self, widget, data):
		if not self.idling:
			GObject.idle_add(self.delayed_motion)
			self.idling = True
			
	def delayed_motion(self):
		try:
			x, y = self.imageview.get_pointer()
			if self.dragging or not DragNavi.RequireClick:
				if self.check_margin(False):
					if self.margin_handling_ref is None:
						self.attach_timeout()
			
				elif self.margin_handling_ref is not None:
					self.remove_timeout()
					fleur_cursor = Gdk.Cursor(Gdk.CursorType.FLEUR)
					self.imageview.get_window().set_cursor(fleur_cursor)
			
				if self.margin_handling_ref is None and self.last_step:
					dx, dy = self.last_step
					dx, dy = x - dx, y - dy
					dx, dy = dx * DragNavi.Speed, dy * DragNavi.Speed
					# Yep, this is done by dividing by magnification.
					if not DragNavi.MagnifySpeed:
						magnification = self.imageview.get_magnification()
						dx, dy = dx / magnification, dy / magnification
										
					if dx:
						hadjust = self.imageview.get_hadjustment()
						vw = hadjust.get_upper() - hadjust.get_lower()
						vw -= hadjust.get_page_size() 
						nx = hadjust.get_value() + dx
			
						if nx < hadjust.get_lower():
							nx = hadjust.get_lower()
						if nx > vw:
							nx = vw
							
						hadjust.set_value(nx)
						
					else:
						x = self.last_step[0]
			
					if dy:
						vadjust = self.imageview.get_vadjustment()
						vh = vadjust.get_upper() - vadjust.get_lower()
						vh -= vadjust.get_page_size()
						ny = vadjust.get_value() + dy
			
						if ny < vadjust.get_lower():
							ny = vadjust.get_lower()
						if ny > vh:
							ny = vh
							
						vadjust.set_value(ny)
									
					else:
						y = self.last_step[1]
				
				self.last_step = x, y
		finally:
			self.idling = False
					
	def margin_handler(self):
		return self.check_margin(True)
		
	def check_margin(self, move):
		x, y = self.imageview.get_pointer()
		allocation = self.imageview.get_allocation()
		
		if allocation.width > DragNavi.Margin * 2:
			xmargin = DragNavi.Margin
		else:
			xmargin = allocation.width / 2
		
		if allocation.height > DragNavi.Margin * 2:
			ymargin = DragNavi.Margin
		else:
			ymargin = allocation.height / 2
		
		if move:
			xshift = yshift = 0
			if x < xmargin:
				xshift = -1
				
			elif x > allocation.width - xmargin:
				xshift = 1
				
			if y < ymargin:
				yshift = -1
			
			elif y > allocation.height - ymargin:
				yshift = 1
			
			elif xshift and allocation.height > ymargin * 4:
				if y < ymargin * 2:
					yshift = -1
				elif y > allocation.height - ymargin * 2:
					yshift = 1
				
			if not xshift and yshift and allocation.width > xmargin * 4:
				if x < xmargin * 2:
					xshift = -1
				elif x > allocation.width - xmargin * 2:
					xshift = 1
			
			if xshift or yshift:
				cursor_type = None
				
				if xshift < 0:
					if yshift < 0:
						cursor_type = Gdk.CursorType.TOP_LEFT_CORNER
					elif yshift > 0:
						cursor_type = Gdk.CursorType.BOTTOM_LEFT_CORNER
					else:
						cursor_type = Gdk.CursorType.LEFT_SIDE
				elif xshift > 0:
					if yshift < 0:
						cursor_type = Gdk.CursorType.TOP_RIGHT_CORNER
					elif yshift > 0:
						cursor_type = Gdk.CursorType.BOTTOM_RIGHT_CORNER
					else:
						cursor_type = Gdk.CursorType.RIGHT_SIDE
				elif yshift < 0:
					cursor_type = Gdk.CursorType.TOP_SIDE
				elif yshift > 0:
					cursor_type = Gdk.CursorType.BOTTOM_SIDE
					
				self.imageview.get_window().set_cursor(Gdk.Cursor(cursor_type))
				
				relatively_current_time = time.time()
				delta_time = relatively_current_time - self.moving_timestamp
				self.moving_timestamp = relatively_current_time
				
				scalar = delta_time * DragNavi.ContinuousSpeed * DragNavi.Speed
				if not DragNavi.MagnifySpeed:
					scalar /= self.imageview.get_magnification()
				xshift, yshift = xshift * scalar, yshift * scalar
				
				hadjust = self.imageview.get_hadjustment()
				vadjust = self.imageview.get_vadjustment()
				for adjust, shift in ((hadjust, xshift), (vadjust, yshift)):
					new_value = adjust.get_value() + shift
					new_value = min(adjust.get_upper() - adjust.get_page_size(),
					                new_value)
					new_value = max(adjust.get_lower(), new_value)
					
					adjust.set_value(new_value)
				
				return True
								
			else:
				self.moving_timestamp = None
				return False
			
		else:
			return x < xmargin or x > allocation.width - xmargin or \
				y < ymargin or y > allocation.height - ymargin
					
	Speed = -1.0
	MagnifySpeed = False
	ContinuousSpeed = 500
	Margin = 24
	RequireClick = True
	Frequency = 0.033
	
	@staticmethod
	def create(imageview):
		return DragNavi(imageview)
	
	@staticmethod
	def get_name():
		return _("Drag")
		
	@staticmethod
	def get_codename():
		return "drag-navi"
	
	@staticmethod
	def get_settings_widgets():
		widgets = Gtk.Grid()
		widgets.set_column_spacing(20)
		widgets.set_row_spacing(5)
		
		# Someone should look up whether it is speed or velocity...
		# Then again we got no inertia here so whatever :D
		speed = Gtk.SpinButton()
		speed_label = Gtk.Label(_("Dragging speed"))
		speed_label.set_alignment(0, 0.5)
		speed_label.set_hexpand(True)
		speed.set_adjustment(Gtk.Adjustment(abs(DragNavi.Speed),
		                     0.1, 10, 0.3, 2, 0))
		speed.set_digits(1)
		widgets.attach(speed_label, 0, 0, 1, 1)
		widgets.attach(speed, 1, 0, 1, 1)
		widgets.speed = speed
		
		# Unexpected dragging mode is unexpected.
		# Maybe I should have allowed for negative speed instead...
		image_drag = Gtk.RadioButton(_("Drag the image"))
		image_drag.set_alignment(0, 0.5)
		view_drag = Gtk.RadioButton(_("Drag the view"))
		view_drag.set_alignment(0, 0.5)
		view_drag.join_group(image_drag)
		
		if DragNavi.Speed < 0:
			image_drag.set_active(True)
		else:
			view_drag.set_active(True)
			
		mode_row = Gtk.HBox()
		mode_row.pack_start(image_drag, False, True, 0)
		mode_row.pack_start(view_drag, False, True, 20)
		
		widgets.attach(mode_row, 0, 1, 2, 1)
		widgets.drag_modes = { "image":image_drag, "view":view_drag }
		
		speed_subrow = Gtk.HBox()
		
		# When this is set, the speed in a 2x zoom image is twice
		# as fast as usual
		magnify = Gtk.CheckButton(_("Magnify speed"))
		magnify.set_active(DragNavi.MagnifySpeed)
		widgets.magnify = magnify
		speed_subrow.pack_start(magnify, False, True, 0)
				
		require_click = Gtk.CheckButton(_("Require click to move"))
		require_click.set_active(DragNavi.RequireClick)
		widgets.require_click = require_click
		speed_subrow.pack_start(require_click, False, True, 20)
		
		widgets.attach(speed_subrow, 0, 2, 2, 1)
		
		# If the mouse is pressed in the margin, it starts dragging...
		# Continuously!
		margin_label = Gtk.Label(_("Continuous dragging margin"))
		margin_label.set_alignment(0, 0.5)
		margin = Gtk.SpinButton()
		margin.set_adjustment(Gtk.Adjustment(DragNavi.Margin, 0, 500, 1, 8, 0))
		widgets.attach(margin_label, 0, 4, 1, 1)
		widgets.attach(margin, 1, 4, 1, 1)
		widgets.margin = margin
		
		# Continuous dragging "speed". Don't even ask me how this works.
		cont_speed_label = Gtk.Label(_("Continuous dragging speed"))
		cont_speed_label.set_alignment(0, 0.5)
		cont_speed = Gtk.SpinButton()
		cont_speed.set_adjustment(Gtk.Adjustment(DragNavi.ContinuousSpeed,
		                                         0.1, 5000, 10, 50, 0))
		cont_speed.set_digits(1)
		widgets.attach(cont_speed_label, 0, 5, 1, 1)
		widgets.attach(cont_speed, 1, 5, 1, 1)
		widgets.cont_speed = cont_speed
		
		# What am I doing here...
		widgets.save_settings = DragNavi.apply_settings.__get__(widgets, None)
		
		return widgets
		
	@staticmethod
	def apply_settings(widgets):
		DragNavi.Margin = widgets.margin.get_value()
		DragNavi.MagnifySpeed = widgets.magnify.get_active()
		DragNavi.RequireClick = widgets.require_click.get_active()
		if widgets.drag_modes["image"].get_active():
			DragNavi.Speed = widgets.speed.get_value() * -1
		else:
			DragNavi.Speed = widgets.speed.get_value()
			
		DragNavi.ContinuousSpeed = widgets.cont_speed.get_value()
		
		set_boolean = preferences.Settings.set_boolean
		set_double = preferences.Settings.set_double
		set_int = preferences.Settings.set_int
		
		set_double("navi-drag-speed", abs(DragNavi.Speed))
		set_boolean("navi-drag-invert", DragNavi.Speed > 0)
		set_boolean("navi-drag-magnify-speed", DragNavi.MagnifySpeed)
		set_boolean("navi-drag-require-click", DragNavi.RequireClick)
		set_int("navi-drag-margin", DragNavi.Margin)
		set_double("navi-drag-continuous-speed", DragNavi.ContinuousSpeed)
		
	@staticmethod
	def load_settings():
		get_boolean = preferences.Settings.get_boolean
		get_double = preferences.Settings.get_double
		get_int = preferences.Settings.get_int
		
		DragNavi.Speed = get_double("navi-drag-speed")
		if not get_boolean("navi-drag-invert"):
			DragNavi.Speed *= -1
		DragNavi.MagnifySpeed = get_boolean("navi-drag-magnify-speed")
		DragNavi.RequireClick = get_boolean("navi-drag-require-click")
		DragNavi.Margin = get_int("navi-drag-margin")
		DragNavi.ContinuousSpeed = get_double("navi-drag-continuous-speed")
	
class RollNavi:
	''' This navigator is almost the same as the DragNavi,
	    except without the dragging part '''
	def __init__(self, imageview):
		self.imageview = imageview
		
		self.roller_ref = None
		self.pointer = None
		self.movement_timestamp = None
		# Setup events
		self.imageview.add_events(
			Gdk.EventMask.LEAVE_NOTIFY_MASK |
			Gdk.EventMask.POINTER_MOTION_MASK |
			Gdk.EventMask.POINTER_MOTION_HINT_MASK)
		
		self.view_handlers = [
			self.imageview.connect("motion-notify-event", self.motion_event),
			self.imageview.connect("leave-notify-event", self.leave_event)
			]
	
	def detach(self):
		for handler in self.view_handlers:
			self.imageview.disconnect(handler)
			
		self.imageview.get_window().set_cursor(None)
	
	def attach_timeout(self):
		self.roller_ref = GLib.timeout_add(int(1000 * RollNavi.Frequency), self.roll)
		self.movement_timestamp = time.time()
	
	def remove_timeout(self):
		GLib.source_remove(self.roller_ref)
		self.roller_ref = None
		self.movement_timestamp = None
	
	def motion_event(self, widget, data):
		# Get the mouse position relative to the center of the imageview
		allocation = self.imageview.get_allocation()
		w, h = allocation.width, allocation.height
		mx, my = self.imageview.get_pointer()
		rx, ry = mx - (w / 2), my - (h / 2)
		# The size of the "sphere"
		r = w / 2 if w > h else h  / 2
		r = max(r - RollNavi.Margin, 1)
		# The distance, aka vector length
		d = (rx ** 2 + ry ** 2) ** 0.5
		self.pointer = rx, ry, d, r
		
		# Check whether it is rolling
		rolling = False
		if d >= RollNavi.Threshold:
			rolling = True
			
		elif mx < RollNavi.Margin or mx > w - RollNavi.Margin or \
		     my < RollNavi.Margin or my > h - RollNavi.Margin:
			rolling = True
			
		if rolling:
			# Create a timeout callback if one doesn't exist
			if self.roller_ref is None:
				self.attach_timeout()
			# Trigonometricksf
			angle = math.atan2(rx, ry)
			angle_index = int(round((angle + math.pi) / (math.pi / 4) - 1))
			cursor_type = (
				Gdk.CursorType.TOP_LEFT_CORNER, 
				Gdk.CursorType.LEFT_SIDE,
				Gdk.CursorType.BOTTOM_LEFT_CORNER,
				Gdk.CursorType.BOTTOM_SIDE,
				Gdk.CursorType.BOTTOM_RIGHT_CORNER,
				Gdk.CursorType.RIGHT_SIDE,
				Gdk.CursorType.TOP_RIGHT_CORNER,
				Gdk.CursorType.TOP_SIDE,
				 )[angle_index]
			
			self.imageview.get_window().set_cursor(Gdk.Cursor(cursor_type))
		else:
			# Cancel timeout callback
			if self.roller_ref is not None:
				self.remove_timeout()
				
			# Reset cursor
			self.imageview.get_window().set_cursor(None)
			
	def leave_event(self, widget, data):
		self.pointer = None
		if self.roller_ref is not None:
			GLib.source_remove(self.roller_ref)
			self.roller_ref = None
			
	def roll(self): # 'n rock
		if self.pointer is None:
			return False
		
		# Calculate roll speed
		rx, ry, d, r = self.pointer
		s = min(1, (d - RollNavi.Threshold) / (r - RollNavi.Threshold))
		s = 1 - (1 - s) ** 3
		s *= RollNavi.Speed
		if not RollNavi.MagnifySpeed:
			s /= self.imageview.get_magnification()
		sx, sy = [min(1, max(-1, v / r)) * s for v in (rx, ry) ]
		# Apply delta
		relatively_current_time = time.time()
		delta_time = relatively_current_time - self.movement_timestamp
		self.movement_timestamp = relatively_current_time
		sx, sy = sx * delta_time, sy * delta_time
		# Move the thing
		hadjust = self.imageview.get_hadjustment()
		vadjust = self.imageview.get_vadjustment()
		
		for adjust, offset in ((hadjust, sx), (vadjust, sy)):
			new_value = adjust.get_value() + offset
			new_value = min(adjust.get_upper() - adjust.get_page_size(),
			                new_value)
			new_value = max(adjust.get_lower(), new_value)
			
			adjust.set_value(new_value)
			
		return True
	
	Frequency = 0.033
	Speed = 750
	MagnifySpeed = False
	Threshold = 16
	Margin = 64
	
	@staticmethod
	def create(imageview):
		return RollNavi(imageview)
	
	@staticmethod
	def get_name():
		return _("Roll")
		
	@staticmethod
	def get_codename():
		return "roll-navi"
		
	@staticmethod
	def get_settings_widgets():
		widgets = Gtk.Grid()
		widgets.set_column_spacing(20)
		widgets.set_row_spacing(5)
		
		# This is the speed on and after the edge of the sphere
		speed_label = Gtk.Label(_("Maximum rolling speed"))
		speed_label.set_alignment(0, 0.5)
		speed_label.set_hexpand(True)
		speed = Gtk.SpinButton()
		speed.set_adjustment(Gtk.Adjustment(RollNavi.Speed,
		                                    10, 10000, 20, 200, 0))
		widgets.attach(speed_label, 0, 0, 1, 1)
		widgets.attach(speed, 1, 0, 1, 1)
		widgets.speed = speed
		
		# Magnify speed, same as DragNavi
		magnify = Gtk.CheckButton(_("Magnify speed"))
		magnify.set_active(RollNavi.MagnifySpeed)
		widgets.attach(magnify, 0, 1, 2, 1)
		widgets.magnify = magnify
		
		# Margins!
		margin_label = Gtk.Label(_("Sphere margin"))
		margin_label.set_alignment(0, 0.5)
		margin = Gtk.SpinButton()
		margin.set_adjustment(Gtk.Adjustment(RollNavi.Margin,
		                                     0, 500, 1, 8, 0))
		widgets.attach(margin_label, 0, 2, 1, 1)
		widgets.attach(margin, 1, 2, 1, 1)
		widgets.margin = margin
		
		# Sometimes you want to settle down, the middle
		threshold_label = Gtk.Label(_("Inner radius"))
		threshold_label.set_alignment(0, 0.5)
		threshold = Gtk.SpinButton()
		threshold.set_adjustment(Gtk.Adjustment(RollNavi.Threshold,
		                                        0, 250, 4, 16, 0))
		widgets.attach(threshold_label, 0, 3, 1, 1)
		widgets.attach(threshold, 1, 3, 1, 1)
		widgets.threshold = threshold
		
		# I still don't have the slightest idea of what I'm doing here
		widgets.save_settings = RollNavi.apply_settings.__get__(widgets, None)
		
		return widgets
		
	@staticmethod
	def apply_settings(widgets):
		RollNavi.Speed = widgets.speed.get_value()
		RollNavi.MagnifySpeed = widgets.magnify.get_active()
		RollNavi.Threshold = widgets.threshold.get_value()
		RollNavi.Margin = widgets.margin.get_value()
		
		set_boolean = preferences.Settings.set_boolean
		set_double = preferences.Settings.set_double
		set_int = preferences.Settings.set_int
		
		set_double("navi-roll-max-speed", RollNavi.Speed)
		set_boolean("navi-roll-magnify-speed", RollNavi.MagnifySpeed)
		set_int("navi-roll-threshold", RollNavi.Threshold)
		set_int("navi-roll-margin", RollNavi.Margin)
	
	@staticmethod
	def load_settings():
		get_boolean = preferences.Settings.get_boolean
		get_double = preferences.Settings.get_double
		get_int = preferences.Settings.get_int
		
		RollNavi.Speed = get_double("navi-roll-max-speed")
		RollNavi.MagnifySpeed = get_boolean("navi-roll-magnify-speed")
		RollNavi.Threshold = get_int("navi-roll-threshold")
		RollNavi.Margin = get_int("navi-roll-margin")
				
class MapNavi:
	''' This navigator adjusts the view so that the adjustment of the image
	    in the view is equal to the mouse position for the view
	    
	    The map mode is either of the following:
	    "stretched": The pointer position is divided by the viewport size and
	                 then scaled to the image size
	    "square": The pointer position is clamped and divided by a square whose
	              side is the smallest of the viewport sides(width or height)
	              and then scaled to the image size
	    "proportional": The pointer position is clamped and divided by a
	                    rectangle proportional to the image size and then to
	                    the image size
	    
	    The margin value is used to clamp before scaling '''
		
	def __init__(self, imageview):
		self.imageview = imageview
		self.idling = False
		
		# Setup events
		self.imageview.add_events(Gdk.EventMask.POINTER_MOTION_MASK |
			Gdk.EventMask.BUTTON_PRESS_MASK |
			Gdk.EventMask.BUTTON_RELEASE_MASK |
			Gdk.EventMask.POINTER_MOTION_HINT_MASK)
		
		self.view_handlers = [
			self.imageview.connect("button-press-event", self.button_press),
			self.imageview.connect("button-release-event", self.button_release),
			self.imageview.connect("motion-notify-event", self.mouse_motion),
			self.imageview.connect("transform-change", self.refresh_adjustments)
		]
		
		crosshair_cursor = Gdk.Cursor(Gdk.CursorType.CROSSHAIR)
		self.imageview.get_window().set_cursor(crosshair_cursor)
		
		self.clicked = False
		self.refresh_adjustments()
		
	def detach(self):		
		for handler in self.view_handlers:
			self.imageview.disconnect(handler)
						
		self.imageview.get_window().set_cursor(None)
	
	def button_press(self, widget=None, data=None):
		if data.button == 1:
			if not self.clicked:
				self.refresh_adjustments()
			
			self.clicked = True
		
	def button_release(self, widget=None, data=None):
		if data.button == 1:
			self.clicked = False
	
	def mouse_motion(self, widget=None, data=None):
		if not self.idling and (not MapNavi.RequireClick or self.clicked):
			GObject.idle_add(self.delayed_refresh)
			self.idling = True
			self.refresh_adjustments()
			
	def delayed_refresh(self):
		try:
			self.refresh_adjustments()
		finally:
			self.idling = False
		
	def get_map_rectangle(self):
		allocation = self.imageview.get_allocation()
		
		allocation.x = allocation.y = MapNavi.Margin
		allocation.width -= MapNavi.Margin * 2
		allocation.height -= MapNavi.Margin * 2
		
		if allocation.width <= 0:
			diff = 1 - allocation.width
			allocation.width += diff
			allocation.x -= diff / 2
			
		if allocation.height <= 0:
			diff = 1 - allocation.height
			allocation.height += diff
			allocation.y -= diff / 2
		
		if MapNavi.MapMode == "square":
			if allocation.width > allocation.height:
				smallest_side = allocation.height
			else:
				smallest_side = allocation.width
			
			half_width_diff = (allocation.width - smallest_side) / 2
			half_height_diff = (allocation.height - smallest_side) / 2
			
			return (allocation.x + half_width_diff,
				    allocation.y + half_height_diff,
				    allocation.width - half_width_diff * 2,
				    allocation.height - half_height_diff * 2)
			
		elif MapNavi.MapMode == "proportional":
			hadjust = self.imageview.get_hadjustment()
			vadjust = self.imageview.get_vadjustment()
			full_width = hadjust.get_upper() - hadjust.get_lower()
			full_height = vadjust.get_upper() - vadjust.get_lower()
			fw_ratio = allocation.width / full_width
			fh_ratio = allocation.height / full_height
						
			if fw_ratio > fh_ratio:
				smallest_ratio = fh_ratio
			else:
				smallest_ratio = fw_ratio
			
			transformed_width = smallest_ratio * full_width
			transformed_height = smallest_ratio * full_height
			
			half_width_diff = (allocation.width - transformed_width) / 2
			half_height_diff = (allocation.height - transformed_height) / 2
			
			return (allocation.x + half_width_diff,
				    allocation.y + half_height_diff,
				    allocation.width - half_width_diff * 2,
				    allocation.height - half_height_diff * 2)
			
		else:
			return (allocation.x, allocation.y,
			        allocation.width, allocation.height)
					
	def refresh_adjustments(self, widget=None, data=None):
		# Clamp mouse pointer to map
		rx, ry, rw, rh = self.get_map_rectangle()
		mx, my = self.imageview.get_pointer()
		x = max(0, min(rw, mx - rx))
		y = max(0, min(rh, my - ry))
		# The adjustments
		hadjust = self.imageview.get_hadjustment()
		vadjust = self.imageview.get_vadjustment()
		# Get content bounding box
		full_width = hadjust.get_upper() - hadjust.get_lower()
		full_height = vadjust.get_upper() - vadjust.get_lower()
		full_width -= hadjust.get_page_size()
		full_height -= vadjust.get_page_size()
		# Transform x and y to picture "adjustment" coordinates
		tx = x / rw * full_width + hadjust.get_lower()
		ty = y / rh * full_height + vadjust.get_lower()
		hadjust.set_value(tx)
		vadjust.set_value(ty)
		
	Margin = 32
	RequireClick = False
	MapMode = "proportional"
	
	Modes = ["stretched", "square", "proportional"]
	
	@staticmethod
	def create(imageview):
		return MapNavi(imageview)
	
	@staticmethod
	def get_name():
		return _("Map")
	
	@staticmethod
	def get_codename():
		return "map-navi"
	
	@staticmethod
	def get_settings_widgets():
		widgets = Gtk.Grid()
		widgets.set_column_spacing(20)
		widgets.set_row_spacing(5)
		
		margin_label = Gtk.Label(_("Map margin"))
		margin_label.set_alignment(0, 0.5)
		margin_label.set_hexpand(True)
		margin = Gtk.SpinButton()
		margin.set_adjustment(Gtk.Adjustment(MapNavi.Margin, 0, 128, 1, 8, 0))
		widgets.attach(margin_label, 0, 0, 1, 1)
		widgets.attach(margin, 1, 0, 1, 1)
		
		require_click = Gtk.CheckButton(_("Require a click to move"))
		require_click.set_active(MapNavi.RequireClick)
		
		widgets.attach(require_click, 0, 1, 2, 1)
		
		stretched_mode = Gtk.RadioButton(_("Use a stretched map"))
		square_mode = Gtk.RadioButton(_("Use a square map"))
		proportional_mode = Gtk.RadioButton(
		                   _("Use a map proportional to the image"))
		
		square_mode.join_group(stretched_mode)
		proportional_mode.join_group(square_mode)
		
		if MapNavi.MapMode == "proportional":
			proportional_mode.set_active(True)
		elif MapNavi.MapMode == "square":
			square_mode.set_active(True)
		else:
			stretched_mode.set_active(True)
		
		mode_vbox = Gtk.VBox()
		mode_vbox.pack_start(stretched_mode, False, False, 0)
		mode_vbox.pack_start(square_mode, False, False, 0)
		mode_vbox.pack_start(proportional_mode, False, False, 0)
		
		mode_align = Gtk.Alignment()
		mode_align.set_padding(0, 0, 20, 0)
		mode_align.add(mode_vbox)
		
		mode_label = Gtk.Label(
		             _("Choose the map figure in relation to the window"))
		mode_label.set_alignment(0, 0.5)
		mode_label.set_line_wrap(True)
		
		widgets.attach(mode_label, 0, 2, 2, 1)
		widgets.attach(mode_align, 0, 3, 2, 1)
		
		widgets.margin = margin
		
		widgets.require_click = require_click
		
		widgets.stretched_mode = stretched_mode
		widgets.square_mode = square_mode
		widgets.proportional_mode = proportional_mode
		
		widgets.save_settings = MapNavi.apply_settings.__get__(widgets, None)
		
		return widgets
		
	@staticmethod
	def apply_settings(widgets):
		MapNavi.Margin = widgets.margin.get_value()
		MapNavi.RequireClick = widgets.require_click.get_active()
		
		set_boolean = preferences.Settings.set_boolean
		set_string = preferences.Settings.set_string
		set_int = preferences.Settings.set_int
		
		if widgets.stretched_mode.get_active():
			MapNavi.MapMode = "stretched"
			set_string("navi-map-mode", "Stretched")
		elif widgets.square_mode.get_active():
			MapNavi.MapMode = "square"
			set_string("navi-map-mode", "Square")
		else:
			MapNavi.MapMode = "proportional"
			set_string("navi-map-mode", "Proportional")
			
		set_int("navi-map-margin", MapNavi.Margin)
		set_boolean("navi-map-require-click", MapNavi.RequireClick)
		
	@staticmethod
	def load_settings():
		get_boolean = preferences.Settings.get_boolean
		get_string = preferences.Settings.get_string
		get_int = preferences.Settings.get_int
		
		MapNavi.Margin = get_int("navi-map-margin")
		MapNavi.RequireClick = get_boolean("navi-map-require-click")
		map_mode_str = get_string("navi-map-mode")
		MapNavi.MapMode = map_mode_str.lower()
	
NaviList.append(DragNavi)
NaviList.append(RollNavi)
NaviList.append(MapNavi)
